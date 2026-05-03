(() => {
  const readLocalStorage = (key) => {
    try {
      return localStorage.getItem(key) || "";
    } catch (error) {
      console.error(`读取 localStorage 失败: ${key}`, error);
      return "";
    }
  };

  const webProtectKey = "security-sdk/s_sdk_sign_data_key/web_protect";
  const keysKey = "security-sdk/s_sdk_crypt_sdk";

  const webProtect = readLocalStorage(webProtectKey);
  const keys = readLocalStorage(keysKey);

  const escapeSingleQuote = (value) =>
    String(value || "").replace(/'/g, "'\\''");

  const escapeTemplateLiteral = (value) =>
    String(value || "")
      .replace(/\\/g, "\\\\")
      .replace(/`/g, "\\`")
      .replace(/\$\{/g, "\\${");

  const envText = [
    `DY_WEB_PROTECT='${escapeSingleQuote(webProtect)}'`,
    `DY_KEYS='${escapeSingleQuote(keys)}'`,
  ].join("\n");

  const copyCommand = `copy(\`${escapeTemplateLiteral(envText)}\`)`;

  console.log("===== DouYin Security Env Export =====");
  console.log(envText);
  console.log("----- copy command -----");
  console.log(copyCommand);
  console.log("======================================");

  if (typeof copy === "function") {
    copy(envText);
    console.log("已复制环境变量到剪贴板。");
  }

  if (!webProtect || !keys) {
    console.warn("未完整读取到 DY_WEB_PROTECT 或 DY_KEYS。请确认：");
    console.warn("1. 当前页面是已登录的 www.douyin.com");
    console.warn("2. 页面已完成安全脚本初始化");
    console.warn("3. 可刷新页面后重试");
  }

  return { DY_WEB_PROTECT: webProtect, DY_KEYS: keys, envText, copyCommand };
})();
