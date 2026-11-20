// Password gate for seller pages that should not be public.
//
// Each protected path reads its password from an environment variable in the
// Vercel project settings. The browser shows its own sign-in box; any user
// name works, only the password is checked. If the variable is not set, the
// page stays closed rather than open.
//
//   /5483  ->  PASSWORD_5483
//
// Vercel Routing Middleware: returning nothing lets the request continue.

export const config = {
  matcher: ["/5483", "/5483.html"],
};

const GATES = { "/5483": "PASSWORD_5483", "/5483.html": "PASSWORD_5483" };

function same(a, b) {
  // Constant-time string compare, so timing does not leak the password.
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

function page(status, title, text, extra) {
  return new Response(
    `<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex"><title>${title}</title><body style="font:16px/1.6 -apple-system,Segoe UI,Roboto,sans-serif;max-width:32rem;margin:15vh auto;padding:0 20px;color:#17202c"><h1 style="font-weight:500;font-size:1.4rem">${title}</h1><p>${text}</p></body>`,
    {
      status,
      headers: Object.assign(
        { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow" },
        extra || {}
      ),
    }
  );
}

export default function middleware(request) {
  const path = new URL(request.url).pathname.replace(/\/$/, "");
  const envName = GATES[path];
  if (!envName) return;

  const password = (process.env[envName] || "").trim();
  if (!password) return page(503, "Not open yet", "This page is not available yet. Please check back soon.");

  const header = request.headers.get("authorization") || "";
  if (header.startsWith("Basic ")) {
    let decoded = "";
    try { decoded = atob(header.slice(6)); } catch (e) { decoded = ""; }
    const given = decoded.slice(decoded.indexOf(":") + 1);
    if (same(given, password)) return;
  }

  return page(401, "Password required", "Enter the password Kevin sent you. Any name works in the user name box.", {
    "WWW-Authenticate": 'Basic realm="5483 Old Franklin", charset="UTF-8"',
  });
}
