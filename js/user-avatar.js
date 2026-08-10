!function () {
  // 2026-08-10 (task #761, AJ: "登入後身份以男女公仔頭 ICON 取代，加自定
  // 名字" -- replace the generic 👤 avatar with a male/female figure icon
  // the user picks, plus an editable display name). Shared by
  // js/nav.js (site-wide Account flyout on function pages) and index.html
  // (homepage's own #userTopbar) so both places render the same icon/name
  // logic instead of drifting apart -- this is the single source of truth
  // for "what does this user's identity look like" across the site.
  //
  // Icons are inline Lucide-style stroke SVGs (matches the rest of the
  // site's topbar icons -- see js/theme-toggle.js's sun/moon for the same
  // convention): a plain head+shoulders glyph for "male"/neutral, and a
  // head+flared-dress silhouette for "female". Neither is meant as a
  // strong stereotype claim -- they're just two visually distinct,
  // recognizable options, matching the common icon-set convention (e.g.
  // Bootstrap Icons' person / person-dress) rather than inventing a new one.
  var ICON_NEUTRAL =
    '<svg width="{S}" height="{S}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" ' +
    'stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="7" r="4"></circle>' +
    '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"></path></svg>';
  var ICON_M =
    '<svg width="{S}" height="{S}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" ' +
    'stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="7" r="4"></circle>' +
    '<path d="M6 21v-1a6 6 0 0 1 12 0v1"></path></svg>';
  var ICON_F =
    '<svg width="{S}" height="{S}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" ' +
    'stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="7" r="4"></circle>' +
    '<path d="M7.5 21c-.3-3 .5-6 1.7-7.5a4 4 0 0 1 5.6 0c1.2 1.5 2 4.5 1.7 7.5"></path></svg>';

  function icon(gender, size) {
    var tpl = gender === "m" ? ICON_M : gender === "f" ? ICON_F : ICON_NEUTRAL;
    return tpl.replace(/\{S\}/g, String(size || 16));
  }

  // 2026-08-10 (AJ clarifying answer: "LINE號太長只顯示你位字，加顯示
  // 男女公仔頭加可改名字" -- LINE's own display name can be long, so show
  // only its first character by default; once the user renames themselves
  // via PUT /auth/profile (name_is_custom becomes true, see backend/auth/
  // auth.py's update_profile()), show the chosen name in full instead).
  // Email/Google/WhatsApp accounts are never auto-truncated -- their
  // stored name already came from a short field the user typed (regName
  // on login.html) or a phone-derived placeholder, not a long profile
  // nickname.
  function displayName(user) {
    if (!user) return "";
    var name = (user.name || "").trim();
    if (!name) return "";
    if (user.oauth_provider === "line" && !user.name_is_custom) {
      var chars = Array.from ? Array.from(name) : name.split("");
      return chars[0] || name.charAt(0);
    }
    return name;
  }

  window.XflAvatar = { icon: icon, displayName: displayName };
}();
