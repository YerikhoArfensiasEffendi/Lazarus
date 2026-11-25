import { Readable } from "node:stream";
import {
  AudioPlayer,
  AudioPlayerStatus,
  createAudioPlayer,
  createAudioResource,
  EndBehaviorType,
  entersState,
  joinVoiceChannel,
  NoSubscriberBehavior,
  VoiceConnection,
  VoiceConnectionStatus,
} from "@discordjs/voice";
import { AttachmentBuilder, Client, VoiceBasedChannel } from "discord.js";
import prism from "prism-media";
import {
  computePcmRms,
  pcm16MonoToWav,
  splitDiscordMessage,
  stereo48kToMono16k,
} from "./audio.js";
import { DmAttachmentPayload, LazarusApiClient } from "./lazarusClient.js";

export interface VoiceSessionConfig {
  silenceMs: number;
  minAudioMs: number;
  minRms: number;
  bargeIn: boolean;
  allowedUserIds: Set<string>;
}

export async function deliverDiscordDm(
  client: Client,
  userId: string,
  title: string,
  content: string,
  skills: string[],
  attachment: DmAttachmentPayload | null,
): Promise<boolean> {
  try {
    const user = await client.users.fetch(userId);
    const dm = await user.createDM();
    const skillFooter =
      skills.length > 0 ? `\n\n_Skills aktif: ${skills.map((s) => `\`${s}\``).join(", ")}_` : "";
    const fullText = `**${title || "Data dari Lazarus"}**\n\n${content}${skillFooter}`.trim();
    const chunks = splitDiscordMessage(fullText, 1900);

    const files: AttachmentBuilder[] = [];
    if (attachment && attachment.content_base64) {
      const fileBuf = Buffer.from(attachment.content_base64, "base64");
      files.push(new AttachmentBuilder(fileBuf, { name: attachment.filename }));
    }

    if (chunks.length === 0 && files.length > 0) {
      await dm.send({ content: `**${title || "File dari Lazarus"}**`, files });
      return true;
    }

    for (let i = 0; i < chunks.length; i++) {
      const isLast = i === chunks.length - 1;
      await dm.send({
        content: chunks[i],
        files: isLast && files.length > 0 ? files : undefined,
      });
    }
    return true;
  } catch (err) {
    console.error(`[Lazarus DM] Failed to DM user ${userId}:`, err);
    return false;
  }
}

export class LazarusVoiceSession {
  readonly guildId: string;
  readonly connection: VoiceConnection;
  readonly player: AudioPlayer;
  private readonly client: Client;
  private readonly api: LazarusApiClient;
  private readonly config: VoiceSessionConfig;
  private readonly activeStreams = new Set<string>();
  private processingTurn = false;
  private destroyed = false;

  constructor(
    client: Client,
    channel: VoiceBasedChannel,
    api: LazarusApiClient,
    config: VoiceSessionConfig,
  ) {
    this.guildId = channel.guild.id;
    this.client = client;
    this.api = api;
    this.config = config;

    this.connection = joinVoiceChannel({
      channelId: channel.id,
      guildId: channel.guild.id,
      adapterCreator: channel.guild.voiceAdapterCreator,
      selfDeaf: false,
      selfMute: false,
      daveEncryption: true,
    });

    this.player = createAudioPlayer({
      behaviors: { noSubscriber: NoSubscriberBehavior.Pause },
    });
    this.connection.subscribe(this.player);
  }

  async start(greetingText: string): Promise<void> {
    await entersState(this.connection, VoiceConnectionStatus.Ready, 20_000);
    this.attachReceiver();

    this.connection.on(VoiceConnectionStatus.Disconnected, async () => {
      if (this.destroyed) return;
      try {
        await Promise.race([
          entersState(this.connection, VoiceConnectionStatus.Signalling, 5_000),
          entersState(this.connection, VoiceConnectionStatus.Connecting, 5_000),
        ]);
      } catch {
        this.stop();
      }
    });

    if (greetingText) {
      await this.speakText(greetingText);
    }
  }

  private attachReceiver(): void {
    const receiver = this.connection.receiver;

    receiver.speaking.on("start", (userId: string) => {
      if (this.destroyed) return;
      if (this.client.user && userId === this.client.user.id) return;
      if (this.config.allowedUserIds.size > 0 && !this.config.allowedUserIds.has(userId)) {
        return;
      }
      if (this.activeStreams.has(userId)) return;

      if (this.config.bargeIn && this.player.state.status === AudioPlayerStatus.Playing) {
        this.player.stop(true);
      }

      this.activeStreams.add(userId);
      const opusStream = receiver.subscribe(userId, {
        end: {
          behavior: EndBehaviorType.AfterSilence,
          duration: this.config.silenceMs,
        },
      });

      const decoder = new prism.opus.Decoder({
        rate: 48000,
        channels: 2,
        frameSize: 960,
      });

      const pcmChunks: Buffer[] = [];
      opusStream.pipe(decoder);

      decoder.on("data", (chunk: Buffer) => {
        pcmChunks.push(chunk);
      });

      const finalize = async () => {
        this.activeStreams.delete(userId);
        if (this.destroyed || pcmChunks.length === 0) return;

        const stereo48k = Buffer.concat(pcmChunks);
        const durationMs = Math.round((stereo48k.length / (48000 * 4)) * 1000);
        if (durationMs < this.config.minAudioMs) return;

        const mono16k = stereo48kToMono16k(stereo48k);
        const rms = computePcmRms(mono16k);
        if (rms < this.config.minRms) return;

        await this.handleUtterance(userId, pcm16MonoToWav(mono16k, 16000), durationMs);
      };

      decoder.once("end", () => {
        void finalize();
      });

      const onError = (err: Error) => {
        this.activeStreams.delete(userId);
        console.warn(`[Lazarus Voice] Audio stream error for ${userId}: ${err.message}`);
      };
      opusStream.once("error", onError);
      decoder.once("error", onError);
    });
  }

  private async handleUtterance(
    userId: string,
    wavBuffer: Buffer,
    durationMs: number,
  ): Promise<void> {
    if (this.processingTurn) {
      console.log(`[Lazarus Voice] Skipping overlapping utterance from ${userId}`);
      return;
    }
    this.processingTurn = true;
    try {
      const user = await this.client.users.fetch(userId).catch(() => null);
      const username = user?.displayName || user?.username || userId;
      console.log(`[Lazarus Voice] Received ${durationMs}ms speech from ${username}...`);

      const turn = await this.api.sendVoiceTurn(wavBuffer, userId, username);
      if (!turn.transcript) return;

      console.log(
        `[Lazarus Voice] ${username}: "${turn.transcript}" -> Lazarus: "${turn.spoken_reply}" ` +
          `(stt=${turn.timings_ms.stt}ms brain=${turn.timings_ms.brain}ms tts=${turn.timings_ms.tts}ms)`,
      );

      const tasks: Promise<unknown>[] = [];
      if (turn.audio_base64) {
        tasks.push(this.playBase64Audio(turn.audio_base64));
      }
      if (turn.should_send_dm && (turn.dm_content || turn.dm_attachment)) {
        tasks.push(
          deliverDiscordDm(
            this.client,
            userId,
            turn.dm_title,
            turn.dm_content,
            turn.matched_skills,
            turn.dm_attachment,
          ),
        );
      }
      await Promise.all(tasks);
    } catch (err) {
      console.error("[Lazarus Voice] Turn processing error:", err);
    } finally {
      this.processingTurn = false;
    }
  }

  async speakText(text: string): Promise<void> {
    try {
      const tts = await this.api.synthesizeSpeech(text);
      if (tts.audio_base64) {
        await this.playBase64Audio(tts.audio_base64);
      }
    } catch (err) {
      console.warn("[Lazarus Voice] TTS greeting failed (backend may still be starting):", err);
    }
  }

  private async playBase64Audio(audioBase64: string): Promise<void> {
    if (this.destroyed) return;
    const buffer = Buffer.from(audioBase64, "base64");
    const resource = createAudioResource(Readable.from(buffer));
    this.player.play(resource);
    await entersState(this.player, AudioPlayerStatus.Playing, 5_000).catch(() => undefined);
  }

  stop(): void {
    if (this.destroyed) return;
    this.destroyed = true;
    this.player.stop(true);
    try {
      this.connection.destroy();
    } catch {
      // Already destroyed.
    }
  }
}
