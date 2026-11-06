/// <reference types="office-js" />
import { ExcelHost } from "./hosts/excel";
import { mount } from "./ui";

Office.onReady(() => {
  mount(new ExcelHost(), document.getElementById("app")!);
});
