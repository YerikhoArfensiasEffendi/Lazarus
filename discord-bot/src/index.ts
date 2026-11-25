import path from "node:path";
import { fileURLToPath } from "node:url";
import { generateDependencyReport } from "@discordjs/voice";
import {
  ChannelType,
  Client,
  Events,
  GatewayIntentBits,
  GuildMember,
  Partials,
  REST,
  Routes,
  SlashCommandBuilder,
} from "discord.js";
import dotenv from "dotenv";
import { splitDiscordMessage } from "./audio.js";
import { LazarusApiClient } from "./lazarusClient.js";
import { deliverDiscordDm, LazarusVoiceSession, VoiceSessionConfig } from "./voiceSession.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
dotenv.config({ path: path.resolve(__dirname, "../../.env") });
dotenv.config();

if (process.argv.includes("--doctor")) {
  console.log("=== Lazarus Discord Voice Dependency Report (DAVE E2EE / Opus / FFmpeg) ===");
  console.log(generateDependencyReport());
  process.exit(0);
}

const token = process.env.DISCORD_BOT_TOKEN?.trim();
if (!token) {
  console.error(
    "[Lazarus Discord] DISCORD_BOT_TOKEN is missing.\n" +
      "Copy .env.example to .env and set DISCORD_BOT_TOKEN (see docs/DISCORD_VOICE_SETUP.md).",
  );
  process.exit(1);
}

const apiBaseUrl = process.env.LAZARUS_API_URL?.trim() || "http://127.0.0.1:8000";
const api = new LazarusApiClient(apiBaseUrl);

const allowedUserIds = new Set(
  (process.env.LAZARUS_ALLOWED_USER_IDS || "")
    .split(",")
    .map((id) => id.trim())
    .filter(Boolean),
);

const voiceConfig: VoiceSessionConfig = {
  silenceMs: Number(process.env.LAZARUS_SILENCE_MS || 850),
  minAudioMs: Number(process.env.LAZARUS_MIN_AUDIO_MS || 450),
  minRms: Number(process.env.LAZARUS_MIN_RMS || 220),
  bargeIn: (process.env.LAZARUS_BARGE_IN || "true").toLowerCase() !== "false",
  allowedUserIds,
};

function isAuthorized(userId: string): boolean {
  return allowedUserIds.size === 0 || allowedUserIds.has(userId);
}

const commands = [
  new SlashCommandBuilder()
    .setName("join")
    .setDescription("Undang Lazarus masuk ke voice channel kamu untuk ngobrol langsung"),
  new SlashCommandBuilder()
    .setName("leave")
    .setDescription("Keluar dari voice channel aktif"),
  new SlashCommandBuilder()
    .setName("ask")
    .setDescription("Tanya Lazarus lewat teks dan terima data lengkap di DM Discord")
    .addStringOption((opt) =>
      opt.setName("pertanyaan").setDescription("Apa yang ingin kamu tanyakan?").setRequired(true),
    ),
  new SlashCommandBuilder()
    .setName("skills")
    .setDescription("Cari skill agentic aktif milik Lazarus")
    .addStringOption((opt) =>
      opt.setName("query").setDescription("Kata kunci (mis. ponytail, pdf, debug)"),
    ),
  new SlashCommandBuilder()
    .setName("status")
    .setDescription("Cek status live Lazarus Brain, Whisper STT, TTS, dan LLM lokal"),
  new SlashCommandBuilder()
    .setName("dm-test")
    .setDescription("Tes kirim pesan DM Discord dari Lazarus ke akun kamu"),
].map((cmd) => cmd.toJSON());

const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildVoiceStates,
    GatewayIntentBits.DirectMessages,
    GatewayIntentBits.MessageContent,
  ],
  partials: [Partials.Channel],
});

const sessions = new Map<string, LazarusVoiceSession>();

client.once(Events.ClientReady, async (readyClient) => {
  console.log(`[Lazarus Discord] Logged in as ${readyClient.user.tag}`);
  console.log(`[Lazarus Discord] Backend API: ${apiBaseUrl}`);
  if (allowedUserIds.size > 0) {
    console.log(`[Lazarus Discord] Access restricted to ${allowedUserIds.size} allowed user ID(s).`);
  }

  const rest = new REST({ version: "10" }).setToken(token);
  const guildId = process.env.DISCORD_GUILD_ID?.trim();
  try {
    if (guildId) {
      await rest.put(Routes.applicationGuildCommands(readyClient.user.id, guildId), {
        body: commands,
      });
      console.log(`[Lazarus Discord] Registered slash commands instantly for guild ${guildId}.`);
    } else {
      await rest.put(Routes.applicationCommands(readyClient.user.id), { body: commands });
      console.log("[Lazarus Discord] Registered global slash commands.");
    }
  } catch (err) {
    console.error("[Lazarus Discord] Slash command registration failed:", err);
  }
});

client.on(Events.InteractionCreate, async (interaction) => {
  if (!interaction.isChatInputCommand()) return;

  if (!isAuthorized(interaction.user.id)) {
    await interaction.reply({
      content: "Maaf, Lazarus saat ini dikonfigurasi khusus untuk pembuatnya saja.",
      ephemeral: true,
    });
    return;
  }

  if (interaction.commandName === "join") {
    const member = interaction.member as GuildMember | null;
    const channel = member?.voice?.channel;
    if (!channel || !interaction.guildId) {
      await interaction.reply({
        content: "Masuk ke salah satu Voice Channel dulu ya, lalu ketik `/join` lagi!",
        ephemeral: true,
      });
      return;
    }

    await interaction.deferReply({ ephemeral: true });
    sessions.get(interaction.guildId)?.stop();

    try {
      const session = new LazarusVoiceSession(client, channel, api, voiceConfig);
      sessions.set(interaction.guildId, session);
      await session.start("Halo! Lazarus sudah masuk voice channel. Silakan langsung ngobrol.");
      await interaction.editReply(
        `Lazarus bergabung di **${channel.name}** (DAVE E2EE aktif). Langsung bicara saja — data/kode lengkap akan otomatis saya kirim ke DM Discord kamu!`,
      );
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      await interaction.editReply(`Gagal bergabung ke voice channel: ${message}`);
    }
    return;
  }

  if (interaction.commandName === "leave") {
    if (!interaction.guildId || !sessions.has(interaction.guildId)) {
      await interaction.reply({ content: "Lazarus sedang tidak berada di voice channel.", ephemeral: true });
      return;
    }
    sessions.get(interaction.guildId)?.stop();
    sessions.delete(interaction.guildId);
    await interaction.reply({ content: "Lazarus keluar dari voice channel. Sampai jumpa!", ephemeral: true });
    return;
  }

  if (interaction.commandName === "dm-test") {
    await interaction.deferReply({ ephemeral: true });
    const ok = await deliverDiscordDm(
      client,
      interaction.user.id,
      "Tes Koneksi DM Lazarus Berhasil",
      "Halo! Ini pesan uji coba dari Lazarus yang berjalan lokal di laptop kamu. Data, kode, dan laporan hasil obrolan voice akan dikirim ke sini.",
      ["lazarus-assistant"],
      null,
    );
    await interaction.editReply(
      ok
        ? "Pesan DM berhasil dikirim! Cek inbox DM kamu."
        : "Gagal mengirim DM. Pastikan pengaturan Privacy Discord mengizinkan DM dari anggota server ini.",
    );
    return;
  }

  if (interaction.commandName === "status") {
    await interaction.deferReply({ ephemeral: true });
    try {
      const st = await api.getVoiceStatus();
      await interaction.editReply(
        [
          "**Lazarus Local Voice Status**",
          `- **STT:** \`${st.stt.engine}\` (device: \`${st.stt.device}\`, lang: \`${st.stt.language}\`)`,
          `- **TTS:** \`${st.tts.provider}\` (voice: \`${st.tts.voice}\`)`,
          `- **LLM:** \`${st.llm.model}\` @ \`${st.llm.base_url}\` (${st.llm.reachable ? "ONLINE" : "OFFLINE"})`,
          `- **Active Skills:** \`${st.skills_available}\``,
        ].join("\n"),
      );
    } catch (err) {
      await interaction.editReply(
        `Tidak bisa menghubungi Lazarus Backend di \`${apiBaseUrl}\`: ${err instanceof Error ? err.message : String(err)}`,
      );
    }
    return;
  }

  if (interaction.commandName === "skills") {
    await interaction.deferReply({ ephemeral: true });
    const query = interaction.options.getString("query") || "";
    try {
      const res = await api.searchSkills(query);
      const top = res.items
        .slice(0, 12)
        .map((s) => `- **${s.name}** (\`${s.category}\`) — ${s.repo}`)
        .join("\n");
      await interaction.editReply(
        `**Lazarus Skills (${res.count} ditemukan${query ? ` untuk "${query}"` : ""})**\n${top || "Tidak ada hasil."}`,
      );
    } catch (err) {
      await interaction.editReply(`Gagal memuat skills: ${err instanceof Error ? err.message : String(err)}`);
    }
    return;
  }

  if (interaction.commandName === "ask") {
    await interaction.deferReply({ ephemeral: true });
    const question = interaction.options.getString("pertanyaan", true);
    try {
      const res = await api.sendTextChat(
        question,
        interaction.user.id,
        interaction.user.displayName || interaction.user.username,
        false,
      );
      if (res.should_send_dm && (res.dm_content || res.dm_attachment)) {
        await deliverDiscordDm(
          client,
          interaction.user.id,
          res.dm_title,
          res.dm_content,
          res.matched_skills,
          res.dm_attachment,
        );
      }
      const dmNote = res.should_send_dm ? "\n\n_Data lengkap sudah saya kirim ke DM kamu._" : "";
      await interaction.editReply(`${res.spoken_reply}${dmNote}`);
    } catch (err) {
      await interaction.editReply(`Error menghubungi Lazarus Brain: ${err instanceof Error ? err.message : String(err)}`);
    }
  }
});

client.on(Events.MessageCreate, async (message) => {
  if (message.author.bot) return;
  if (message.channel.type !== ChannelType.DM) return;
  if (!isAuthorized(message.author.id)) return;
  if (!message.content.trim()) return;

  try {
    await message.channel.sendTyping();
    const res = await api.sendTextChat(
      message.content,
      message.author.id,
      message.author.displayName || message.author.username,
      false,
    );
    const body = res.dm_content || res.spoken_reply;
    const chunks = splitDiscordMessage(body, 1900);
    for (const chunk of chunks) {
      await message.reply(chunk);
    }
    if (res.dm_attachment) {
      await deliverDiscordDm(
        client,
        message.author.id,
        res.dm_title || "Lampiran Lazarus",
        "",
        res.matched_skills,
        res.dm_attachment,
      );
    }
  } catch (err) {
    await message.reply(
      `Maaf, Lazarus Backend sedang tidak terjangkau (${err instanceof Error ? err.message : String(err)}).`,
    );
  }
});

void client.login(token);
