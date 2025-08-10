import fetch from "node-fetch";

export async function handler() {
  const username = process.env.TRAINFINDER_USERNAME;
  const password = process.env.TRAINFINDER_PASSWORD;

  if (!username || !password) {
    return {
      statusCode: 500,
      body: JSON.stringify({ error: "TrainFinder credentials not set" })
    };
  }

  try {
    // 1️⃣ Login to TrainFinder
    const loginRes = await fetch("https://trainfinder.otenko.com/Login/Login", {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded"
      },
      body: `Username=${encodeURIComponent(username)}&Password=${encodeURIComponent(password)}`
    });

    const cookies = loginRes.headers.raw()["set-cookie"];
    const authCookie = cookies.find(c => c.startsWith(".ASPXAUTH"));
    if (!authCookie) throw new Error("Login failed — no auth cookie returned");

    // 2️⃣ Fetch live train data
    const trainsRes = await fetch("https://trainfinder.otenko.com/Home/GetViewPortData", {
      method: "POST",
      headers: {
        "cookie": authCookie,
        "x-requested-with": "XMLHttpRequest",
        "accept": "application/json, text/javascript, */*; q=0.01"
      }
    });

    const trainsJson = await trainsRes.json();

    return {
      statusCode: 200,
      body: JSON.stringify(trainsJson)
    };

  } catch (err) {
    return {
      statusCode: 500,
      body: JSON.stringify({ error: err.message })
    };
  }
}