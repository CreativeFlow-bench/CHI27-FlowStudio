/* Runtime API endpoints. Production builds do not bake VITE_API_BASE.
 * 5184 = local Vite, 5173 = GPU static preview, anything else (AutoDL 8443) = same origin. */
(function () {
  var port = window.location.port;
  var protocol = window.location.protocol;
  var hostname = window.location.hostname;
  var wsProtocol = protocol === "https:" ? "wss:" : "ws:";
  if (port === "5184") {
    window.__FLOWSTUDIO_API_BASE__ = protocol + "//" + hostname + ":18001";
    window.__FLOWSTUDIO_WS_BASE__ = wsProtocol + "//" + hostname + ":18001";
    return;
  }
  if (port === "5173") {
    window.__FLOWSTUDIO_API_BASE__ = protocol + "//" + hostname + ":18000";
    window.__FLOWSTUDIO_WS_BASE__ = wsProtocol + "//" + hostname + ":18000";
    return;
  }
  window.__FLOWSTUDIO_API_BASE__ = window.location.origin;
  window.__FLOWSTUDIO_WS_BASE__ = window.location.origin.replace(/^http/i, "ws");
})();
