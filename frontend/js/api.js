const LifeLinkAPI = (() => {
  const TOKEN_KEY = "lifelink_access_token";
  const USER_KEY = "lifelink_user_profile";
  let cachedConfig = null;

  function getToken() {
    return localStorage.getItem(TOKEN_KEY) || "";
  }

  function setSession(token, user) {
    if (token) {
      localStorage.setItem(TOKEN_KEY, token);
    }
    if (user) {
      localStorage.setItem(USER_KEY, JSON.stringify(user));
    }
  }

  function clearSession() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  }

  function getStoredUser() {
    const raw = localStorage.getItem(USER_KEY);
    if (!raw) return null;
    try {
      return JSON.parse(raw);
    } catch {
      return null;
    }
  }

  async function request(path, options = {}) {
    const headers = { ...(options.headers || {}) };
    if (!(options.body instanceof FormData) && !headers["Content-Type"]) {
      headers["Content-Type"] = "application/json";
    }
    const token = getToken();
    if (token && !headers["Authorization"]) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    let response;
    try {
      response = await fetch(path, { cache: options.cache || "no-store", ...options, headers });
    } catch {
      throw new Error("Network error: unable to reach LifeLink server. Check your internet connection.");
    }

    const contentType = response.headers.get("content-type") || "";
    const data = contentType.includes("application/json")
      ? await response.json().catch(() => ({}))
      : {};

    if (!response.ok) {
      let message = "Request failed.";
      if (typeof data.detail === "string") {
        message = data.detail;
      } else if (Array.isArray(data.detail) && data.detail.length > 0) {
        message = data.detail.map((item) => item.msg || String(item)).join("; ");
      }
      const err = new Error(message);
      err.status = response.status;
      err.data = data;
      throw err;
    }

    return data;
  }

  async function getPublicConfig() {
    if (cachedConfig) return cachedConfig;
    cachedConfig = await request("/api/config/public");
    return cachedConfig;
  }

  return {
    request,
    getPublicConfig,
    getToken,
    setSession,
    clearSession,
    getStoredUser,
  };
})();
