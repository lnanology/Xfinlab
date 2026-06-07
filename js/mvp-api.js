async function postApi(path, payload) {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`API 錯誤: ${response.status} ${text}`);
  }

  const data = await response.json();
  if (data.status !== 'ok') {
    throw new Error(data.message || 'API 回傳失敗');
  }

  return data;
}
