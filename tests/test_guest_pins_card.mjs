import fs from "node:fs";
import vm from "node:vm";

class Element {
  constructor() {
    this.shadowRoot = null;
  }
  attachShadow() {
    const elements = new Map();
    let html = "";
    const weekdays = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
      .map((value) => ({ value, checked: false, addEventListener() {} }));
    const root = {
      get innerHTML() {
        return html;
      },
      set innerHTML(value) {
        html = value;
        elements.clear();
        weekdays.forEach((input) => { input.checked = false; });
      },
      querySelector(selector) {
        if (!elements.has(selector)) {
          elements.set(selector, {
            value: {
              "#activation": "temporary",
              "#recurring-start": "12:00",
              "#recurring-end": "13:00",
            }[selector] || "",
            hidden: false,
            dataset: {},
            addEventListener() {},
          });
        }
        return elements.get(selector);
      },
      querySelectorAll(selector) {
        if (selector === "input[name=weekday]") return weekdays;
        if (selector === "input[name=weekday]:checked") return weekdays.filter((input) => input.checked);
        return [];
      },
    };
    this.shadowRoot = root;
    return root;
  }
  dispatchEvent() {}
}

const registry = new Map();
const context = vm.createContext({
  HTMLElement: Element,
  CustomEvent: class {},
  customElements: {
    define(name, klass) {
      if (registry.has(name)) throw new Error(`duplicate ${name}`);
      registry.set(name, klass);
    },
    get(name) {
      return registry.get(name);
    },
  },
  window: { customCards: [] },
  navigator: { clipboard: { async writeText() {} } },
  confirm: () => false,
  console,
  Date,
  setTimeout,
  clearTimeout,
});

const source = fs.readFileSync(process.argv[2], "utf8");
vm.runInContext(source, context, { filename: process.argv[2] });
const Card = registry.get("smartrent-guest-pins-card");
if (!Card) throw new Error("card was not registered");
if (context.window.customCards.filter((card) => card.type === "smartrent-guest-pins-card").length !== 1) {
  throw new Error("card metadata was duplicated");
}

const calls = [];
const card = new Card();
card.setConfig({ title: "Guest PINs", entity: "lock.front_door" });
card._hass = {
  async callWS(message) {
    calls.push(message);
    if (message.service === "get_guest_codes") {
      return {
        response: {
          "lock.front_door": {
            guest_codes: [],
            config: {
              max_permanent_codes: 0,
              max_temporary_codes: 10,
              max_temporary_hours: 48,
              max_recurring_codes: 10,
              max_recurring_days: 5,
              max_recurring_window_hours: 2,
            },
          },
        },
      };
    }
    if (message.service === "create_guest_code") {
      return {
        response: {
          "lock.front_door": {
            verified: true,
            guest_code: { code_id: 123, pin: "123456" },
          },
        },
      };
    }
    throw new Error(`unexpected service ${message.service}`);
  },
};
await card._refresh();
if (!card.shadowRoot.innerHTML.includes("Create guest PIN")) throw new Error("create form missing");
if (!card.shadowRoot.innerHTML.includes("No guest PINs")) throw new Error("empty state missing");
if (card.shadowRoot.innerHTML.includes('value="permanent"')) throw new Error("disabled permanent option shown");
if (calls.length !== 1 || calls[0].return_response !== true) throw new Error("response service call invalid");
if (calls[0].target?.entity_id !== "lock.front_door") throw new Error("wrong lock target");

const firstName = card.shadowRoot.querySelector("#first-name");
firstName.value = "Ada";
card.hass = { ...card._hass };
if (card.shadowRoot.querySelector("#first-name") !== firstName || firstName.value !== "Ada") {
  throw new Error("routine hass update rebuilt the form");
}

card._render();
if (card.shadowRoot.querySelector("#first-name").value !== "Ada") {
  throw new Error("explicit render discarded the form draft");
}

card.shadowRoot.querySelector("#last-name").value = "Lovelace";
card.shadowRoot.querySelector("#email").value = "ada@example.test";
card.shadowRoot.querySelector("#start-at").value = "2026-08-16T12:00";
card.shadowRoot.querySelector("#end-at").value = "2026-08-16T13:00";
await card._create();
const createCall = calls.find((call) => call.service === "create_guest_code");
if (!createCall || createCall.service_data.first_name !== "Ada" || createCall.service_data.last_name !== "Lovelace") {
  throw new Error("create action discarded the form draft");
}
if (createCall.service_data.email !== "ada@example.test" || createCall.service_data.activation_type !== "temporary") {
  throw new Error("create action sent incorrect form data");
}

console.log(JSON.stringify({ registered: true, rendered: true, serviceCall: true, formStable: true, createDraftPreserved: true, htmlBytes: card.shadowRoot.innerHTML.length }));
