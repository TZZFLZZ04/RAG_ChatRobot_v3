const apiPrefix = "/api/v1";
const tokenStorageKey = "chatrobot_access_token";

const elements = {
  form: document.getElementById("registerStandaloneForm"),
  usernameInput: document.getElementById("registerStandaloneUsernameInput"),
  emailInput: document.getElementById("registerStandaloneEmailInput"),
  passwordInput: document.getElementById("registerStandalonePasswordInput"),
  notice: document.getElementById("registerNotice"),
  toast: document.getElementById("toast"),
};

function showToast(message, isError = false) {
  elements.toast.textContent = message;
  elements.toast.style.background = isError ? "rgba(143, 50, 23, 0.94)" : "rgba(31, 27, 22, 0.9)";
  elements.toast.classList.remove("hidden");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    elements.toast.classList.add("hidden");
  }, 2600);
}

function setNotice(message) {
  if (!message) {
    elements.notice.classList.add("hidden");
    elements.notice.textContent = "";
    return;
  }
  elements.notice.textContent = message;
  elements.notice.classList.remove("hidden");
}

async function parseResponsePayload(response) {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  return response.text();
}

async function assertOkResponse(response) {
  if (response.ok) {
    return response;
  }

  const payload = await parseResponsePayload(response);
  const message = typeof payload === "string" ? payload : payload.message || "请求失败";
  throw new Error(message);
}

async function request(url, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.delete("Authorization");
  const response = await fetch(url, { ...options, headers });
  await assertOkResponse(response);
  return parseResponsePayload(response);
}

async function handleRegisterSubmit(event) {
  event.preventDefault();
  try {
    await request(`${apiPrefix}/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: elements.usernameInput.value.trim(),
        email: elements.emailInput.value.trim(),
        password: elements.passwordInput.value,
      }),
    });
    window.localStorage.removeItem(tokenStorageKey);
    window.location.href = "/?registered=1";
  } catch (error) {
    const message = error.message || "注册失败";
    setNotice(message);
    showToast(message, true);
  }
}

function bootstrap() {
  if (window.localStorage.getItem(tokenStorageKey)) {
    window.location.replace("/");
    return;
  }
  setNotice("");
  elements.form.addEventListener("submit", handleRegisterSubmit);
}

bootstrap();
