/**
 * Fast, zero-dependency PCM/WAV audio utilities and Discord DM message chunking.
 */

export function stereo48kToMono16k(pcm48kStereo: Buffer): Buffer {
  // 48kHz stereo 16-bit LE = 4 bytes per stereo frame; downsample 3:1 to 16kHz mono (2 bytes/frame).
  const totalStereoFrames = Math.floor(pcm48kStereo.length / 4);
  const outFrames = Math.floor(totalStereoFrames / 3);
  const out = Buffer.alloc(outFrames * 2);

  for (let i = 0; i < outFrames; i++) {
    const baseFrame = i * 3;
    let sum = 0;
    for (let k = 0; k < 3; k++) {
      const byteOffset = (baseFrame + k) * 4;
      const left = pcm48kStereo.readInt16LE(byteOffset);
      const right = pcm48kStereo.readInt16LE(byteOffset + 2);
      sum += (left + right) / 2;
    }
    const sample = Math.max(-32768, Math.min(32767, Math.round(sum / 3)));
    out.writeInt16LE(sample, i * 2);
  }
  return out;
}

export function computePcmRms(pcm16: Buffer): number {
  const samples = Math.floor(pcm16.length / 2);
  if (samples === 0) return 0;
  let sumSq = 0;
  for (let i = 0; i < samples; i++) {
    const val = pcm16.readInt16LE(i * 2);
    sumSq += val * val;
  }
  return Math.sqrt(sumSq / samples);
}

export function pcm16MonoToWav(pcm16Mono: Buffer, sampleRate = 16000): Buffer {
  const numChannels = 1;
  const bitsPerSample = 16;
  const byteRate = (sampleRate * numChannels * bitsPerSample) / 8;
  const blockAlign = (numChannels * bitsPerSample) / 8;
  const header = Buffer.alloc(44);

  header.write("RIFF", 0);
  header.writeUInt32LE(36 + pcm16Mono.length, 4);
  header.write("WAVE", 8);
  header.write("fmt ", 12);
  header.writeUInt32LE(16, 16);
  header.writeUInt16LE(1, 20); // PCM
  header.writeUInt16LE(numChannels, 22);
  header.writeUInt32LE(sampleRate, 24);
  header.writeUInt32LE(byteRate, 28);
  header.writeUInt16LE(blockAlign, 32);
  header.writeUInt16LE(bitsPerSample, 34);
  header.write("data", 36);
  header.writeUInt32LE(pcm16Mono.length, 40);

  return Buffer.concat([header, pcm16Mono]);
}

export function splitDiscordMessage(text: string, maxLen = 1900): string[] {
  const trimmed = text.trim();
  if (!trimmed) return [];
  if (trimmed.length <= maxLen) return [trimmed];

  const chunks: string[] = [];
  let remaining = trimmed;
  while (remaining.length > maxLen) {
    let cut = remaining.lastIndexOf("\n", maxLen);
    if (cut < Math.floor(maxLen * 0.4)) {
      cut = remaining.lastIndexOf(" ", maxLen);
    }
    if (cut <= 0) {
      cut = maxLen;
    }
    chunks.push(remaining.slice(0, cut).trim());
    remaining = remaining.slice(cut).trim();
  }
  if (remaining) {
    chunks.push(remaining);
  }
  return chunks;
}
