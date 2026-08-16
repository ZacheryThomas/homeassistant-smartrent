const CARD_VERSION = "1.0.1";

class SmartRentGuestPinsCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._codes = [];
    this._policy = {};
    this._busy = false;
    this._error = "";
    this._created = null;
    this._loaded = false;
  }

  setConfig(config) {
    if (!config?.entity || !String(config.entity).startsWith("lock.")) {
      throw new Error("A SmartRent lock entity is required");
    }
    this._config = { title: "Guest PINs", ...(config || {}) };
    this._render();
  }

  set hass(hass) {
    const firstUpdate = !this._hass;
    this._hass = hass;
    if (firstUpdate) {
      this._render();
      if (!this._loaded && !this._busy) this._refresh();
    }
  }

  getCardSize() {
    return Math.max(5, this._codes.length + 4);
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, min_rows: 5 };
  }

  _escape(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  _toast(message) {
    const event = new CustomEvent("hass-notification", {
      bubbles: true,
      composed: true,
      detail: { message },
    });
    this.dispatchEvent(event);
  }

  async _call(service, serviceData = {}) {
    if (!this._hass) throw new Error("Home Assistant is unavailable");
    const entityId = this._config.entity;
    const result = await this._hass.callWS({
      type: "call_service",
      domain: "smartrent",
      service,
      target: { entity_id: entityId },
      service_data: serviceData,
      return_response: true,
    });
    const response = result?.response?.[entityId];
    if (!response || typeof response !== "object") {
      throw new Error("SmartRent returned no response for the lock");
    }
    return response;
  }

  async _withBusy(action) {
    this._busy = true;
    this._error = "";
    this._render();
    try {
      await action();
    } catch (error) {
      console.error("SmartRent guest PIN card", error);
      this._error = error?.message || String(error);
      this._toast(this._error);
    } finally {
      this._busy = false;
      this._render();
    }
  }

  async _refresh() {
    await this._withBusy(async () => {
      const response = await this._call("get_guest_codes");
      this._codes = Array.isArray(response.guest_codes) ? response.guest_codes : [];
      this._policy = response.config || {};
      this._created = null;
      this._loaded = true;
    });
  }

  _formData() {
    const root = this.shadowRoot;
    const activation = root.querySelector("#activation").value;
    const data = {
      activation_type: activation,
      first_name: root.querySelector("#first-name").value.trim(),
      last_name: root.querySelector("#last-name").value.trim(),
    };
    const phone = root.querySelector("#phone").value.trim();
    const email = root.querySelector("#email").value.trim();
    if (phone) data.phone = phone;
    if (email) data.email = email;
    if (activation === "temporary") {
      data.start_at = new Date(root.querySelector("#start-at").value).toISOString();
      data.end_at = new Date(root.querySelector("#end-at").value).toISOString();
    }
    if (activation === "recurring") {
      data.recurring_start_time = `${root.querySelector("#recurring-start").value}:00`;
      data.recurring_end_time = `${root.querySelector("#recurring-end").value}:00`;
      data.recurring_days = [...root.querySelectorAll("input[name=weekday]:checked")]
        .map((input) => input.value);
    }
    return data;
  }

  async _create() {
    await this._withBusy(async () => {
      const data = this._formData();
      if (!data.first_name || !data.last_name) {
        throw new Error("First and last name are required");
      }
      if (!data.phone && !data.email) {
        throw new Error("Phone or email is required");
      }
      const response = await this._call("create_guest_code", data);
      if (!response.verified || !response.guest_code?.pin) {
        throw new Error("SmartRent did not return a verified PIN");
      }
      this._created = response.guest_code;
      const refreshed = await this._call("get_guest_codes");
      this._codes = refreshed.guest_codes || [];
      this._policy = refreshed.config || this._policy;
      this._toast("Guest PIN created and verified");
    });
  }

  async _delete(codeId, name) {
    if (!confirm(`Delete the guest PIN for ${name}?`)) return;
    await this._withBusy(async () => {
      const response = await this._call("delete_guest_code", { code_id: codeId });
      if (!response.verified || !response.deleted) {
        throw new Error("SmartRent did not verify deletion");
      }
      const refreshed = await this._call("get_guest_codes");
      this._codes = refreshed.guest_codes || [];
      this._policy = refreshed.config || this._policy;
      this._created = null;
      this._toast("Guest PIN deleted and verified");
    });
  }

  async _copy(pin) {
    try {
      await navigator.clipboard.writeText(String(pin));
      this._toast("PIN copied to clipboard");
    } catch (_error) {
      this._toast("Clipboard access was denied");
    }
  }

  _setDefaults() {
    const now = new Date();
    const end = new Date(now.getTime() + 2 * 60 * 60 * 1000);
    const localValue = (date) => {
      const offset = date.getTimezoneOffset() * 60000;
      return new Date(date.getTime() - offset).toISOString().slice(0, 16);
    };
    const start = this.shadowRoot?.querySelector("#start-at");
    const finish = this.shadowRoot?.querySelector("#end-at");
    if (start && !start.value) start.value = localValue(now);
    if (finish && !finish.value) finish.value = localValue(end);
  }

  _captureFormState() {
    const root = this.shadowRoot;
    if (!root?.querySelector("#activation")) return null;
    const value = (id) => root.querySelector(`#${id}`)?.value ?? "";
    return {
      activation: value("activation"),
      firstName: value("first-name"),
      lastName: value("last-name"),
      email: value("email"),
      phone: value("phone"),
      startAt: value("start-at"),
      endAt: value("end-at"),
      recurringStart: value("recurring-start"),
      recurringEnd: value("recurring-end"),
      recurringDays: [...root.querySelectorAll("input[name=weekday]:checked")]
        .map((input) => input.value),
    };
  }

  _restoreFormState(state) {
    if (!state) return;
    const root = this.shadowRoot;
    const setValue = (id, value) => {
      const input = root.querySelector(`#${id}`);
      if (input) input.value = value;
    };
    setValue("activation", state.activation);
    setValue("first-name", state.firstName);
    setValue("last-name", state.lastName);
    setValue("email", state.email);
    setValue("phone", state.phone);
    setValue("start-at", state.startAt);
    setValue("end-at", state.endAt);
    setValue("recurring-start", state.recurringStart);
    setValue("recurring-end", state.recurringEnd);
    root.querySelectorAll("input[name=weekday]").forEach((input) => {
      input.checked = state.recurringDays.includes(input.value);
    });
    root.querySelector("#temporary-fields").hidden = state.activation !== "temporary";
    root.querySelector("#recurring-fields").hidden = state.activation !== "recurring";
  }

  _codeCard(code) {
    const name = `${code.first_name || "Guest"} ${code.last_name || ""}`.trim();
    const schedule = code.activation_type === "temporary"
      ? `${this._formatDate(code.start_at)} → ${this._formatDate(code.end_at)}`
      : code.activation_type === "recurring"
        ? `${(code.recurring_days || []).join(", ")} · ${code.recurring_start_time || ""}–${code.recurring_end_time || ""}`
        : "Permanent";
    return `<article class="code">
      <div class="code-head"><div><strong>${this._escape(name)}</strong><div class="muted">${this._escape(schedule)}</div></div><span class="badge">${this._escape(code.activation_type || "guest")}</span></div>
      <div class="pin-row"><code>${this._escape(code.pin || "••••")}</code><button class="secondary copy" data-pin="${this._escape(code.pin || "")}">Copy</button><button class="danger delete" data-id="${Number(code.code_id)}" data-name="${this._escape(name)}">Delete</button></div>
      <div class="muted">ID ${Number(code.code_id)}${code.provisioning_status ? ` · ${this._escape(code.provisioning_status)}` : ""}</div>
    </article>`;
  }

  _formatDate(value) {
    if (!value) return "—";
    const date = new Date(value);
    return Number.isNaN(date.valueOf()) ? String(value) : date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
  }

  _render() {
    if (!this.shadowRoot || !this._config) return;
    const formState = this._captureFormState();
    const permanentDisabled = Number(this._policy.max_permanent_codes) === 0;
    this.shadowRoot.innerHTML = `<style>
      :host{display:block} ha-card{padding:18px} h1{font-size:22px;margin:0} h2{font-size:17px;margin:18px 0 10px}.top{display:flex;justify-content:space-between;gap:12px;align-items:center}.muted{color:var(--secondary-text-color);font-size:13px}.policy{margin:10px 0;padding:10px 12px;border-radius:10px;background:var(--secondary-background-color);font-size:13px}.error{margin:10px 0;padding:10px;border-radius:8px;background:rgba(244,67,54,.13);color:var(--error-color)}.created{padding:14px;border:2px solid var(--success-color,#4caf50);border-radius:12px;margin:12px 0}.created code,.pin-row code{font-size:24px;letter-spacing:.14em;font-weight:700}.form{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}label{display:flex;flex-direction:column;gap:5px;font-size:13px;color:var(--secondary-text-color)}input,select{box-sizing:border-box;width:100%;padding:11px;border:1px solid var(--divider-color);border-radius:8px;background:var(--card-background-color);color:var(--primary-text-color);font:inherit}.wide{grid-column:1/-1}.weekdays{display:flex;flex-wrap:wrap;gap:8px}.weekdays label{display:flex;flex-direction:row;align-items:center;padding:7px 9px;border:1px solid var(--divider-color);border-radius:8px}.weekdays input{width:auto}.actions{display:flex;gap:9px;margin-top:12px;flex-wrap:wrap}button{border:0;border-radius:9px;padding:10px 13px;background:var(--primary-color);color:var(--text-primary-color,#fff);font:inherit;font-weight:600;cursor:pointer}button.secondary{background:var(--secondary-background-color);color:var(--primary-text-color)}button.danger{background:var(--error-color);color:#fff}button:disabled{opacity:.5;cursor:wait}.code{border-top:1px solid var(--divider-color);padding:14px 0}.code-head,.pin-row{display:flex;align-items:center;justify-content:space-between;gap:10px}.pin-row{justify-content:flex-start;margin:10px 0}.badge{padding:5px 8px;border-radius:999px;background:var(--secondary-background-color);font-size:12px}.empty{padding:18px;text-align:center;color:var(--secondary-text-color)}@media(max-width:600px){.form{grid-template-columns:1fr}.wide{grid-column:auto}.top{align-items:flex-start}.pin-row{flex-wrap:wrap}}
    </style><ha-card>
      <div class="top"><div><h1>${this._escape(this._config.title)}</h1><div class="muted">SmartRent · ${this._escape(this._config.entity)}</div></div><button class="secondary" id="refresh" ${this._busy ? "disabled" : ""}>${this._busy ? "Working…" : "Refresh"}</button></div>
      <div class="policy">Temporary: ${this._escape(this._policy.max_temporary_codes ?? "—")} codes, ${this._escape(this._policy.max_temporary_hours ?? "—")} h max · Recurring: ${this._escape(this._policy.max_recurring_codes ?? "—")} codes, ${this._escape(this._policy.max_recurring_days ?? "—")} days/week, ${this._escape(this._policy.max_recurring_window_hours ?? "—")} h/day${permanentDisabled ? " · Permanent disabled" : ""}</div>
      ${this._error ? `<div class="error">${this._escape(this._error)}</div>` : ""}
      ${this._created ? `<div class="created"><strong>New verified PIN</strong><div class="pin-row"><code>${this._escape(this._created.pin)}</code><button class="secondary copy" data-pin="${this._escape(this._created.pin)}">Copy</button></div><div class="muted">Save it now; refreshing hides this notice.</div></div>` : ""}
      <h2>Create guest PIN</h2><div class="form">
        <label>Type<select id="activation"><option value="temporary">Temporary</option><option value="recurring">Recurring</option>${permanentDisabled ? "" : '<option value="permanent">Permanent</option>'}</select></label>
        <label>First name<input id="first-name" autocomplete="off"></label><label>Last name<input id="last-name" autocomplete="off"></label>
        <label>Email<input id="email" type="email" autocomplete="off"></label><label>Phone<input id="phone" type="tel" autocomplete="off"></label>
        <div id="temporary-fields" class="wide form"><label>Starts<input id="start-at" type="datetime-local"></label><label>Ends<input id="end-at" type="datetime-local"></label></div>
        <div id="recurring-fields" class="wide" hidden><div class="form"><label>Daily start<input id="recurring-start" type="time" value="12:00"></label><label>Daily end<input id="recurring-end" type="time" value="13:00"></label></div><label style="margin-top:10px">Days<div class="weekdays">${["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"].map((day) => `<label><input type="checkbox" name="weekday" value="${day}">${day.slice(0,3)}</label>`).join("")}</div></label></div>
      </div><div class="actions"><button id="create" ${this._busy ? "disabled" : ""}>Create & verify PIN</button></div>
      <h2>Existing guest PINs</h2>${this._loaded && this._codes.length === 0 ? '<div class="empty">No guest PINs</div>' : this._codes.map((code) => this._codeCard(code)).join("")}
    </ha-card>`;
    this.shadowRoot.querySelector("#refresh")?.addEventListener("click", () => this._refresh());
    this.shadowRoot.querySelector("#create")?.addEventListener("click", () => this._create());
    const activation = this.shadowRoot.querySelector("#activation");
    activation?.addEventListener("change", () => {
      this.shadowRoot.querySelector("#temporary-fields").hidden = activation.value !== "temporary";
      this.shadowRoot.querySelector("#recurring-fields").hidden = activation.value !== "recurring";
    });
    this.shadowRoot.querySelectorAll(".copy").forEach((button) => button.addEventListener("click", () => this._copy(button.dataset.pin)));
    this.shadowRoot.querySelectorAll(".delete").forEach((button) => button.addEventListener("click", () => this._delete(Number(button.dataset.id), button.dataset.name)));
    this._setDefaults();
    this._restoreFormState(formState);
  }
}

if (!customElements.get("smartrent-guest-pins-card")) {
  customElements.define("smartrent-guest-pins-card", SmartRentGuestPinsCard);
}
window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === "smartrent-guest-pins-card")) {
  window.customCards.push({
    type: "smartrent-guest-pins-card",
    name: "SmartRent Guest PINs",
    description: "Create, list, copy, and delete verified SmartRent guest PINs.",
    preview: false,
  });
}
console.info(`SmartRent Guest PINs Card ${CARD_VERSION}`);
