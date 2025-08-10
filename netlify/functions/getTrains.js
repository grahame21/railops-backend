// netlify/functions/getTrains.js
// Proxies TrainFinder viewport data with your stored .ASPXAUTH cookie

const fetch = (...args) => import('node-fetch').then(({default: f}) => f(...args));

exports.handler = async (event) => {
  try {
    // Read query params (fallbacks keep it harmless if caller forgets them)
    const { lat = "-34.9285", lng = "138.6007", zm = "8" } = event.queryStringParameters || {};

    const authCookie = process.env.TF_AUTH_COOKIE; // <- set this in Netlify env
    if (!authCookie) {
      return {
        statusCode: 500,
        body: JSON.stringify({ error: "TF_AUTH_COOKIE not set in environment." }),
      };
    }

    // Same endpoint TrainFinder calls from the site
    const url = "https://trainfinder.otenko.com/Home/GetViewPortData";

    // Build headers TrainFinder expects (pared down to the useful ones)
    const headers = {
      "accept": "*/*",
      "x-requested-with": "XMLHttpRequest",
      "origin": "https://trainfinder.otenko.com",
      "referer": `https://trainfinder.otenko.com/home/nextlevel?lat=${lat}&lng=${lng}&zm=${zm}`,
      "cookie": `.ASPXAUTH=${authCookie}`,
    };

    // TrainFinder’s endpoint is a POST with no body
    const resp = await fetch(url, { method: "POST", headers });

    if (!resp.ok) {
      const text = await resp.text();
      return {
        statusCode: resp.status,
        body: JSON.stringify({
          error: "TrainFinder responded with an error",
          status: resp.status,
          body: text.slice(0, 5000),
        }),
      };
    }

    // Should be JSON already
    const data = await resp.json();

    // Return JSON to the browser
    return {
      statusCode: 200,
      headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
      body: JSON.stringify(data),
    };
  } catch (err) {
    return {
      statusCode: 500,
      body: JSON.stringify({ error: err.message || String(err) }),
    };
  }
};