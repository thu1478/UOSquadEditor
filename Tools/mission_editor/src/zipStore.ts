/** Uncompressed ZIP (store method). No extra dependency. */

const CRC_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();

function crc32(data: Uint8Array): number {
  let c = 0xffffffff;
  for (let i = 0; i < data.length; i++) {
    c = CRC_TABLE[(c ^ data[i]) & 0xff] ^ (c >>> 8);
  }
  return (c ^ 0xffffffff) >>> 0;
}

function u16(n: number): Uint8Array {
  const b = new Uint8Array(2);
  new DataView(b.buffer).setUint16(0, n, true);
  return b;
}

function u32(n: number): Uint8Array {
  const b = new Uint8Array(4);
  new DataView(b.buffer).setUint32(0, n >>> 0, true);
  return b;
}

function concat(parts: Uint8Array[]): Uint8Array {
  const len = parts.reduce((n, p) => n + p.length, 0);
  const out = new Uint8Array(len);
  let o = 0;
  for (const p of parts) {
    out.set(p, o);
    o += p.length;
  }
  return out;
}

const enc = new TextEncoder();

export function zipStore(
  files: { path: string; text: string }[]
): Blob {
  const locals: Uint8Array[] = [];
  const centrals: Uint8Array[] = [];
  let offset = 0;
  for (const file of files) {
    const name = enc.encode(file.path.replace(/\\/g, "/"));
    const data = enc.encode(file.text);
    const crc = crc32(data);
    const local = concat([
      u32(0x04034b50),
      u16(20),
      u16(0),
      u16(0),
      u16(0),
      u16(0),
      u32(crc),
      u32(data.length),
      u32(data.length),
      u16(name.length),
      u16(0),
      name,
      data,
    ]);
    const central = concat([
      u32(0x02014b50),
      u16(20),
      u16(20),
      u16(0),
      u16(0),
      u16(0),
      u16(0),
      u32(crc),
      u32(data.length),
      u32(data.length),
      u16(name.length),
      u16(0),
      u16(0),
      u16(0),
      u16(0),
      u32(0),
      u32(offset),
      name,
    ]);
    locals.push(local);
    centrals.push(central);
    offset += local.length;
  }
  const central = concat(centrals);
  const end = concat([
    u32(0x06054b50),
    u16(0),
    u16(0),
    u16(files.length),
    u16(files.length),
    u32(central.length),
    u32(offset),
    u16(0),
  ]);
  const bytes = concat([...locals, central, end]);
  const copy = new Uint8Array(bytes.byteLength);
  copy.set(bytes);
  return new Blob([copy], { type: "application/zip" });
}

async function inflateRaw(data: Uint8Array): Promise<Uint8Array> {
  const copy = new Uint8Array(data.byteLength);
  copy.set(data);
  const ds = new DecompressionStream("deflate-raw");
  const copyBuf = new ArrayBuffer(copy.byteLength);
  new Uint8Array(copyBuf).set(copy);
  const stream = new Blob([copyBuf]).stream().pipeThrough(ds);
  const buf = await new Response(stream).arrayBuffer();
  return new Uint8Array(buf) as Uint8Array;
}

/** Read JSON/text files out of a zip (store or deflate). */
export async function unzipTextFiles(
  buf: ArrayBuffer
): Promise<{ name: string; text: string }[]> {
  const bytes = new Uint8Array(buf);
  const dv = new DataView(buf);
  const dec = new TextDecoder();
  const out: { name: string; text: string }[] = [];
  let i = 0;
  while (i + 30 <= bytes.length) {
    const sig = dv.getUint32(i, true);
    if (sig === 0x02014b50 || sig === 0x06054b50) break;
    if (sig !== 0x04034b50) break;
    const method = dv.getUint16(i + 8, true);
    const comp = dv.getUint32(i + 18, true);
    const nameLen = dv.getUint16(i + 26, true);
    const extraLen = dv.getUint16(i + 28, true);
    const name = dec.decode(bytes.subarray(i + 30, i + 30 + nameLen));
    const start = i + 30 + nameLen + extraLen;
    const packed = bytes.subarray(start, start + comp);
    i = start + comp;
    if (!name.toLowerCase().endsWith(".json") && !name.toLowerCase().endsWith(".txt") && !name.toLowerCase().endsWith(".md") && !name.toLowerCase().endsWith(".pchtxt")) {
      continue;
    }
    let raw: Uint8Array;
    if (method === 8) raw = await inflateRaw(packed);
    else if (method === 0) raw = packed;
    else continue;
    out.push({ name, text: dec.decode(raw) });
  }
  return out;
}
