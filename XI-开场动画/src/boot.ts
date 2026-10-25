import { bootMotion } from "./boot-motion";
import { BootLettering } from "./boot-lettering";

const ns = "http://www.w3.org/2000/svg";
const arc = (r: number, start: number, sweep: number, x = 960, y = 540) => {
  const point = (a: number) => `${x + Math.cos(a) * r},${y + Math.sin(a) * r}`;
  if (sweep >= Math.PI * 1.999)
    return `M${point(start)}A${r},${r} 0 1 1 ${point(start + Math.PI)}A${r},${r} 0 1 1 ${point(start + Math.PI * 2)}`;
  return `M${point(start)}A${r},${r} 0 ${sweep > Math.PI ? 1 : 0} 1 ${point(start + sweep)}`;
};

export class BootSequence {
  private welcome: HTMLElement;
  private heading: HTMLElement;
  private company: HTMLElement;
  private highlight: HTMLElement;
  private highlightInk: HTMLElement;
  private scan: HTMLElement;
  private group: SVGGElement;
  private paths: SVGPathElement[];
  private orbitDots: SVGCircleElement[];
  private core: SVGCircleElement;
  private satellites: SVGCircleElement[];
  private caps: SVGCircleElement[];
  private values = new WeakMap<Element, Map<string, string>>();
  private step = "";

  constructor(private stage: HTMLElement) {
    const el = <T extends Element>(s: string) => stage.querySelector<T>(s)!;
    this.welcome = el(".welcome"); this.heading = el(".welcome-heading");
    this.company = el(".welcome-company"); this.highlight = el(".welcome-highlight");
    this.highlightInk = el(".welcome-highlight span"); this.scan = el(".scan");
    this.group = el(".scan g"); this.paths = [...stage.querySelectorAll<SVGPathElement>(".scan path")];
    this.orbitDots = [...stage.querySelectorAll<SVGCircleElement>(".orbit-dot")];
    this.core = el(".scan-core");
    const dot = (fill: string) => {
      const node = document.createElementNS(ns, "circle");
      node.setAttribute("fill", fill); node.setAttribute("stroke", "none");
      node.setAttribute("r", "0"); return node;
    };
    this.satellites = Array.from({ length: 6 }, () => {
      const node = dot("#f2f0ec"); node.classList.add("satellite-dot");
      this.group.insertBefore(node, this.core); return node;
    });
    this.caps = ["#f2f0ec", "#6f6f6b"].map(fill => {
      const node = dot(fill); this.group.append(node); return node;
    });
    new BootLettering(this.heading, ["welcome"]).setText("WELCOME TO");
  }
  private changed(el: Element, key: string, value: string) {
    let map = this.values.get(el);
    if (!map) { map = new Map(); this.values.set(el, map); }
    if (map.get(key) === value) return false;
    map.set(key, value); return true;
  }
  private style(el: HTMLElement | SVGElement, key: string, value: string | number) {
    const text = String(value);
    if (this.changed(el, "style:" + key, text)) el.style.setProperty(key, text);
  }
  private attr(el: Element, key: string, value: string | number) {
    const text = String(value);
    if (this.changed(el, key, text)) el.setAttribute(key, text);
  }
  update(time: number) {
    const s = bootMotion(time);
    if (this.stage.dataset.bootFrame !== String(s.f)) this.stage.dataset.bootFrame = String(s.f);
    if (s.step !== this.step) {
      this.step = s.step; this.stage.dataset.boot = s.step;
      this.style(this.scan, "display", s.scanVisible ? "block" : "none");
      this.style(this.welcome, "display", s.welcomeVisible ? "block" : "none");
    }
    if (s.scan) this.renderScan(s.scan);
    if (s.welcomeVisible) {
      this.style(this.welcome, "opacity", s.welcomeOpacity);
      const gray = Math.round(242 * s.welcomeInk);
      this.style(this.heading, "color", `rgb(${gray} ${gray} ${gray})`);
      this.style(this.company, "opacity", s.companyVisible ? s.companyMask ? .65 : 1 : 0);
      this.style(this.highlightInk, "opacity", s.companyMask ? .06 : 1);
      this.style(this.highlight, "clip-path", `inset(0 ${100 * (1 - s.highlight)}% 0 0)`);
    }
    return s;
  }
  private renderScan(s: NonNullable<ReturnType<typeof bootMotion>["scan"]>) {
    const scan = s.geometry, orbit = s.orbit;
    this.style(this.scan, "opacity", 1);
    this.attr(this.group, "transform", s.scale === 1 ? "" : `translate(960 540) scale(${s.scale}) translate(-960 -540)`);
    this.style(this.group, "opacity", s.opacity);
    this.style(this.group, "filter", s.blur ? `blur(${s.blur}px)` : "none");
    this.attr(this.paths[0], "d", arc(scan.radius, scan.outerStart, scan.outerSweep));
    this.attr(this.paths[1], "d", arc(scan.whiteRadius, scan.whiteStart, scan.whiteSweep));
    this.attr(this.paths[2], "d", arc(scan.innerRadius, scan.innerStart, scan.innerSweep));
    this.attr(this.paths[3], "d", arc(scan.innerRadius, scan.innerStart + Math.PI, scan.innerSweep));
    orbit.sides.forEach((side, i) => {
      this.attr(this.paths[i + 4], "d", arc(side.radius, side.start, side.sweep, side.x, side.y));
      this.style(this.paths[i + 4], "opacity", orbit.sideVisible ? 1 : 0);
    });
    orbit.satellites.forEach((point, i) => {
      this.attr(this.satellites[i], "cx", point.x); this.attr(this.satellites[i], "cy", point.y);
      this.attr(this.satellites[i], "r", point.radius);
    });
    this.style(this.core, "opacity", s.ornament ? 1 : 0);
    this.attr(this.core, "r", orbit.coreRadius);
    this.orbitDots.forEach((dot, i) => {
      this.attr(dot, "cx", 960 + Math.cos(scan.orbit + i * Math.PI) * scan.orbitRadius);
      this.attr(dot, "cy", 540 + Math.sin(scan.orbit + i * Math.PI) * scan.orbitRadius);
      this.attr(dot, "r", scan.dotRadius);
    });
    this.caps.forEach((cap, i) => {
      const angle = i ? scan.whiteStart : scan.outerStart + scan.outerSweep;
      const radius = i ? scan.whiteRadius : scan.radius;
      this.attr(cap, "cx", 960 + Math.cos(angle) * radius);
      this.attr(cap, "cy", 540 + Math.sin(angle) * radius);
      this.attr(cap, "r", i ? scan.whiteCap : scan.blackCap);
    });
  }
}
