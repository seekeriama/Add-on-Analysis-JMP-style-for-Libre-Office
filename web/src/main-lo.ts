import { HttpHost } from "./hosts/http";
import { mount } from "./ui";

mount(new HttpHost(), document.getElementById("app")!);
