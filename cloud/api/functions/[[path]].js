// Every request goes to the one hub object. CORS headers and the key check are done inside it.
// ?room=name picks a separate hub (the contract test uses "test"); with no room it is "main", the one everybody shares.
export async function onRequest({ request, env }) {
  const room = new URL(request.url).searchParams.get("room") || "main";
  return env.HUB.get(env.HUB.idFromName(room)).fetch(request);
}
