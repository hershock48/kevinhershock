// Receives a seller's answers from a pricing report page and emails them to
// Kevin through Resend, from the verified glazedweb.com domain.
//
// Env (Vercel project settings):
//   RESEND_API_KEY  a sending-only Resend key for this project
//   ANSWERS_TO      optional, defaults to kevin@glazedweb.com
//   ANSWERS_FROM    optional, defaults to "Pricing Reports <reports@glazedweb.com>"
//
// Without a key this answers 503, and the page falls back to a prefilled email.

const PAGES = { "130Turnberry": "130 Turnberry Ln" };
const LABELS = {
  lower: "Lower level",
  bath: "Bathroom added",
  roof: "Roof",
  hvac: "Furnace and A/C",
  heater: "Water heater",
  interior: "Kitchen and bath updates",
  extras: "Added outside or for comfort",
  issues: "Inspection concerns",
  timing: "Timing",
};

const clip = (v, n) => String(v == null ? "" : v).slice(0, n).trim();
const money = (n) => "$" + Math.round(Number(n) || 0).toLocaleString("en-US");
const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

module.exports = async (req, res) => {
  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    return res.status(405).json({ ok: false });
  }

  let body = req.body;
  if (typeof body === "string") {
    try { body = JSON.parse(body); } catch { body = null; }
  }
  if (!body || typeof body !== "object") return res.status(400).json({ ok: false });

  // A filled honeypot is a bot; answer as if it worked so it does not retry.
  if (clip(body.website, 200)) return res.status(200).json({ ok: true });

  const address = Object.prototype.hasOwnProperty.call(PAGES, body.page) ? PAGES[body.page] : null;
  if (!address) return res.status(400).json({ ok: false });

  const key = (process.env.RESEND_API_KEY || "").trim();
  if (!key) return res.status(503).json({ ok: false, reason: "not configured" });

  const picks = body.picks && typeof body.picks === "object" ? body.picks : {};
  const rows = Object.keys(LABELS).map((k) => [LABELS[k], clip(picks[k], 200) || "(not answered)"]);
  const name = clip(body.name, 80);
  const contact = clip(body.contact, 120);
  const note = clip(body.note, 1500);
  const figures = [
    ["Estimated value", money(body.value)],
    ["Suggested list", money(body.list)],
    ["Expected sale", money(body.low) + " to " + money(body.high)],
  ];

  const text = [
    `Answers for ${address}`,
    "",
    ...rows.map(([k, v]) => `${k}: ${v}`),
    "",
    ...figures.map(([k, v]) => `${k}: ${v}`),
    "",
    `Name: ${name || "(not given)"}`,
    `Contact: ${contact || "(not given)"}`,
    note ? `\nNotes:\n${note}` : "",
  ].join("\n");

  const tr = ([k, v]) => `<tr><td style="padding:6px 12px 6px 0;color:#555">${esc(k)}</td><td style="padding:6px 0"><strong>${esc(v)}</strong></td></tr>`;
  const html = `<div style="font-family:Arial,sans-serif;font-size:15px;color:#17202c">
<h2 style="font-weight:normal">Answers for ${esc(address)}</h2>
<table style="border-collapse:collapse">${rows.map(tr).join("")}</table>
<h3 style="margin-top:20px">What the answers do to the price</h3>
<table style="border-collapse:collapse">${figures.map(tr).join("")}</table>
<p><strong>Name:</strong> ${esc(name || "(not given)")}<br><strong>Contact:</strong> ${esc(contact || "(not given)")}</p>
${note ? `<p><strong>Notes:</strong><br>${esc(note).replace(/\n/g, "<br>")}</p>` : ""}
</div>`;

  const email = {
    from: process.env.ANSWERS_FROM || "Pricing Reports <reports@glazedweb.com>",
    to: [process.env.ANSWERS_TO || "kevin@glazedweb.com"],
    subject: `${address}: seller answers${name ? " from " + name : ""}`,
    text,
    html,
  };
  if (/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(contact)) email.reply_to = contact;

  try {
    const r = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
      body: JSON.stringify(email),
    });
    if (!r.ok) {
      console.error("resend failed", r.status, await r.text());
      return res.status(502).json({ ok: false });
    }
    return res.status(200).json({ ok: true });
  } catch (err) {
    console.error("resend error", err);
    return res.status(502).json({ ok: false });
  }
};
