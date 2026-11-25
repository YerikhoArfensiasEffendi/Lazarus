import { describe, expect, it, vi } from "vitest";
import {
  computePcmRms,
  pcm16MonoToWav,
  splitDiscordMessage,
  stereo48kToMono16k,
} from "./audio.js";
import { LazarusApiClient } from "./lazarusClient.js";

describe("Discord voice audio utilities", () => {
  it("downsamples 48kHz stereo PCM to 16kHz mono PCM cleanly", () => {
    // 6 stereo frames at 48kHz -> 2 mono frames at 16kHz (4 bytes output)
    const stereo = Buffer.alloc(6 * 4);
    for (let i = 0; i < 6; i++) {
      stereo.writeInt16LE(1000, i * 4);
      stereo.writeInt16LE(2000, i * 4 + 2);
    }
    const mono = stereo48kToMono16k(stereo);
    expect(mono.length).toBe(4);
    expect(mono.readInt16LE(0)).toBe(1500);
    expect(mono.readInt16LE(2)).toBe(1500);
  });

  it("wraps mono PCM in a valid RIFF WAV header and computes RMS", () => {
    const pcm = Buffer.alloc(100);
    for (let i = 0; i < 50; i++) {
      pcm.writeInt16LE(500, i * 2);
    }
    expect(Math.round(computePcmRms(pcm))).toBe(500);

    const wav = pcm16MonoToWav(pcm, 16000);
    expect(wav.toString("ascii", 0, 4)).toBe("RIFF");
    expect(wav.toString("ascii", 8, 12)).toBe("WAVE");
    expect(wav.readUInt32LE(24)).toBe(16000);
    expect(wav.length).toBe(44 + pcm.length);
  });

  it("chunks long Discord DM payloads safely under 2000 characters", () => {
    const longText = Array.from({ length: 50 }, (_, i) => `Baris data ke-${i}: ${"x".repeat(60)}`).join("\n");
    const chunks = splitDiscordMessage(longText, 1900);
    expect(chunks.length).toBeGreaterThan(1);
    for (const chunk of chunks) {
      expect(chunk.length).toBeLessThanOrEqual(1900);
    }
  });

  it("posts voice turns to the local Lazarus Python backend", async () => {
    const mockFetch = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({
        transcript: "Halo Lazarus",
        language: "id",
        spoken_reply: "Halo! Ada yang bisa saya bantu?",
        audio_base64: "QUJD",
        audio_mime: "audio/mpeg",
        should_send_dm: true,
        dm_title: "Tes",
        dm_content: "Data siap.",
        dm_attachment: null,
        matched_skills: ["ponytail"],
        timings_ms: { stt: 100, brain: 200, tts: 50 },
      }),
    })) as unknown as typeof fetch;

    const client = new LazarusApiClient("http://127.0.0.1:8000/", mockFetch);
    const res = await client.sendVoiceTurn(Buffer.from("RIFFDATA"), "u1", "Yerikho");
    expect(res.transcript).toBe("Halo Lazarus");
    expect(res.should_send_dm).toBe(true);
    expect(mockFetch).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/voice/turn",
      expect.objectContaining({ method: "POST" }),
    );
  });
});
