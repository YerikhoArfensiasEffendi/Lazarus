/**
 * Typed HTTP client connecting the local Discord Voice Bot to Lazarus Python Brain API.
 */

export interface DmAttachmentPayload {
  filename: string;
  content_base64: string;
  mime_type?: string;
}

export interface VoiceTurnResponse {
  transcript: string;
  language: string;
  spoken_reply: string;
  audio_base64: string;
  audio_mime: string;
  tts_error?: string | null;
  should_send_dm: boolean;
  dm_title: string;
  dm_content: string;
  dm_attachment: DmAttachmentPayload | null;
  matched_skills: string[];
  provider?: string;
  model?: string;
  timings_ms: { stt: number; brain: number; tts: number };
}

export interface BrainChatResponse {
  spoken_reply: string;
  should_send_dm: boolean;
  dm_title: string;
  dm_content: string;
  dm_attachment: DmAttachmentPayload | null;
  matched_skills: string[];
  recalled_memories: number;
  provider: string;
  model: string;
  latency_ms: number;
  safety_status: string;
}

export interface TTSResponse {
  engine: string;
  voice: string;
  mime_type: string;
  duration_ms: number;
  audio_base64: string;
}

export interface VoiceStatusResponse {
  stt: { engine: string; device: string; language: string };
  tts: { provider: string; voice: string; piper_model_ready: boolean };
  llm: { base_url: string; model: string; reachable: boolean };
  skills_available: number;
}

export class LazarusApiClient {
  private readonly baseUrl: string;
  private readonly fetchImpl: typeof fetch;

  constructor(baseUrl = "http://127.0.0.1:8000", fetchImpl: typeof fetch = fetch) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.fetchImpl = fetchImpl;
  }

  async sendVoiceTurn(
    wavBuffer: Buffer,
    userId: string,
    username: string,
  ): Promise<VoiceTurnResponse> {
    const form = new FormData();
    const audioCopy = new Uint8Array(wavBuffer.length);
    audioCopy.set(wavBuffer);
    form.append("audio", new Blob([audioCopy], { type: "audio/wav" }), "speech.wav");
    form.append("user_id", userId);
    form.append("username", username);

    const resp = await this.fetchImpl(`${this.baseUrl}/voice/turn`, {
      method: "POST",
      body: form,
    });
    if (!resp.ok) {
      throw new Error(`Lazarus /voice/turn failed (${resp.status}): ${await resp.text()}`);
    }
    return (await resp.json()) as VoiceTurnResponse;
  }

  async sendTextChat(
    message: string,
    userId: string,
    username: string,
    voiceMode = false,
  ): Promise<BrainChatResponse> {
    const resp = await this.fetchImpl(`${this.baseUrl}/brain/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: userId,
        username,
        message,
        voice_mode: voiceMode,
      }),
    });
    if (!resp.ok) {
      throw new Error(`Lazarus /brain/chat failed (${resp.status}): ${await resp.text()}`);
    }
    return (await resp.json()) as BrainChatResponse;
  }

  async synthesizeSpeech(text: string): Promise<TTSResponse> {
    const resp = await this.fetchImpl(`${this.baseUrl}/voice/tts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!resp.ok) {
      throw new Error(`Lazarus /voice/tts failed (${resp.status}): ${await resp.text()}`);
    }
    return (await resp.json()) as TTSResponse;
  }

  async getVoiceStatus(): Promise<VoiceStatusResponse> {
    const resp = await this.fetchImpl(`${this.baseUrl}/voice/status`);
    if (!resp.ok) {
      throw new Error(`Lazarus /voice/status failed (${resp.status})`);
    }
    return (await resp.json()) as VoiceStatusResponse;
  }

  async searchSkills(query = ""): Promise<{
    count: number;
    items: Array<{ name: string; category: string; repo: string; description: string }>;
  }> {
    const resp = await this.fetchImpl(
      `${this.baseUrl}/skills?q=${encodeURIComponent(query)}`,
    );
    if (!resp.ok) {
      throw new Error(`Lazarus /skills failed (${resp.status})`);
    }
    return (await resp.json()) as {
      count: number;
      items: Array<{ name: string; category: string; repo: string; description: string }>;
    };
  }
}
