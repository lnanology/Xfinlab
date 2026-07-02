const API_BASE = "https://web-production-86882.up.railway.app";

async function postApi(path, payload) {
  const response = await fetch(API_BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`API 錯誤: ${response.status} ${text}`);
  }
  const data = await response.json();
  return { status: 'ok', data: data.data || data };
}

async function getApi(path) {
  const response = await fetch(API_BASE + path);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`API 錯誤: ${response.status} ${text}`);
  }
  const data = await response.json();
  return { status: 'ok', data: data.data || data };
}
