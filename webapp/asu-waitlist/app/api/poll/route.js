import { kv } from "@vercel/kv";

const TRPC_URL = "https://trydatedrop.com/api/trpc/waitlist.signup?batch=1";
const EMAIL = "abc@asu.edu";

function parseJsonl(text) {
  const lines = text.trim().split("\n").filter(Boolean);
  return lines.map((l) => JSON.parse(l));
}

function findSuccessObject(obj) {
  if (!obj) return null;

  if (Array.isArray(obj)) {
    for (const item of obj) {
      const found = findSuccessObject(item);
      if (found) return found;
    }
    return null;
  }

  if (typeof obj === "object") {
    if (obj.success === true && ("schoolRank" in obj || "schoolSignupCount" in obj)) {
      return obj;
    }
    for (const v of Object.values(obj)) {
      const found = findSuccessObject(v);
      if (found) return found;
    }
  }

  return null;
}

export async function GET(req) {
  const auth = req.headers.get("authorization");
  if (process.env.CRON_SECRET && auth !== `Bearer ${process.env.CRON_SECRET}`) {
    return new Response("Unauthorized", { status: 401 });
  }

  const payload = { "0": { json: { email: EMAIL } } };

  const res = await fetch(TRPC_URL, {
    method: "POST",
    headers: {
      "accept": "*/*",
      "content-type": "application/json",
      "origin": "https://trydatedrop.com",
      "referer": "https://trydatedrop.com/",
      "trpc-accept": "application/jsonl",
      "x-trpc-source": "nextjs-react"
    },
    body: JSON.stringify(payload)
  });

  const text = await res.text();

  let record = null;
  try {
    const parsed = parseJsonl(text);
    record = findSuccessObject(parsed);
  } catch (e) {
    record = null;
  }

  const snapshot = {
    timestampUtc: new Date().toISOString(),
    httpStatus: res.status,
    emailUsed: EMAIL,
    schoolName: record?.schoolName ?? null,
    schoolRank: record?.schoolRank ?? null,
    schoolSignupCount: record?.schoolSignupCount ?? null,
    studentGovEmail: record?.studentGovEmail ?? null,
    studentGovInstagram: record?.studentGovInstagram ?? null,
    rawResponse: text
  };

  await kv.set("asu:latest", snapshot);

  return Response.json({ ok: true, stored: snapshot });
}
