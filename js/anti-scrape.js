// 2026-07-22 fix: this blocked right-click for everyone including the
// site owner (AJ), who needs right-click/copy for their own testing
// ("你先免左我用滑鼠可右COPY選項 只有我可以" -- exempt only me). Skip
// the block when the logged-in user's stored email matches the owner's.
(function () {
  var OWNER_EMAIL = "abcoaj888@gmail.com";
  function isOwner() {
    try {
      var u = JSON.parse(localStorage.getItem("xfinlab_user") || "{}");
      return !!(u && u.email && u.email.toLowerCase() === OWNER_EMAIL);
    } catch (e) {
      return false;
    }
  }
  document.addEventListener("contextmenu", function (e) {
    if (isOwner()) return;
    e.preventDefault();
  });
})();
