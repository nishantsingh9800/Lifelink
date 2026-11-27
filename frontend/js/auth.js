const LifeLinkAuth = (() => {
  async function fetchCurrentUser() {
    if (!LifeLinkAPI.getToken()) return null;
    try {
      const user = await LifeLinkAPI.request("/api/auth/me");
      LifeLinkAPI.setSession(LifeLinkAPI.getToken(), user);
      return user;
    } catch (err) {
      if (err.status === 401 || err.status === 403) {
        LifeLinkAPI.clearSession();
      }
      return null;
    }
  }

  async function requireAuth(allowedRoles = null) {
    const user = await fetchCurrentUser();
    if (!user) {
      window.location.href = "/pages/login.html";
      return null;
    }
    if (Array.isArray(allowedRoles) && !allowedRoles.includes(user.role)) {
      return { forbidden: true, user };
    }
    return { forbidden: false, user };
  }

  async function logout() {
    try {
      if (LifeLinkAPI.getToken()) {
        await LifeLinkAPI.request("/api/auth/logout", { method: "POST" });
      }
    } catch {
      // Clear local session regardless of network errors
    } finally {
      LifeLinkAPI.clearSession();
      window.location.href = "/pages/login.html";
    }
  }

  return {
    fetchCurrentUser,
    requireAuth,
    logout,
  };
})();
