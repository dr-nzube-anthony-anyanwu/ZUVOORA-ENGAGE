/** Decorative line icons (inline SVG, 24×24, currentColor). Always hidden from assistive tech. */
import type { ReactNode } from "react";

function Icon({ children }: { children: ReactNode }) {
  return (
    <svg className="icon" viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor"
         strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      {children}
    </svg>
  );
}

export const IconMoon = () => <Icon><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" /></Icon>;
export const IconInbox = () => (
  <Icon><path d="M4 13l2.5-7h11L20 13v5a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z" /><path d="M4 13h4l1.5 2.5h5L16 13h4" /></Icon>
);
export const IconCalendar = () => (
  <Icon><rect x="3.5" y="5" width="17" height="15" rx="2" /><path d="M3.5 10h17M8 3v4M16 3v4" /></Icon>
);
export const IconUsers = () => (
  <Icon><circle cx="9" cy="8" r="3.2" /><path d="M3 19c.6-3.3 3-5 6-5s5.4 1.7 6 5" /><path d="M16 5.5a3 3 0 0 1 0 5.6M18 14.3c1.5.7 2.6 2.3 3 4.7" /></Icon>
);
export const IconChat = () => (
  <Icon><path d="M5 18.5V6.5A2.5 2.5 0 0 1 7.5 4h9A2.5 2.5 0 0 1 19 6.5v6A2.5 2.5 0 0 1 16.5 15H9z" /><path d="M9 8.5h6M9 11.5h4" /></Icon>
);
export const IconShield = () => (
  <Icon><path d="M12 3l7 3v5.5c0 4.3-2.9 7.9-7 9.5-4.1-1.6-7-5.2-7-9.5V6z" /><path d="M9 12l2 2 4-4" /></Icon>
);
export const IconBook = () => (
  <Icon><path d="M5 4.5h9.5A2.5 2.5 0 0 1 17 7v13H7.5A2.5 2.5 0 0 1 5 17.5z" /><path d="M5 17.5A2.5 2.5 0 0 1 7.5 15H17M19 7v13" /></Icon>
);
export const IconHandshake = () => (
  <Icon><path d="M3 12l4-4 4 2 2-2 4 1 4 3" /><path d="M7 8l-3 5 5 5 2-1 2 1 5-5" /><path d="M10 13l2 2M12 11l3 3" /></Icon>
);
export const IconChart = () => (
  <Icon><path d="M4 20V4M4 20h16" /><path d="M8 16v-4M12 16V8M16 16v-6" /></Icon>
);
export const IconSettings = () => (
  <Icon><circle cx="12" cy="12" r="3" /><path d="M12 3v2.5M12 18.5V21M3 12h2.5M18.5 12H21M5.6 5.6l1.8 1.8M16.6 16.6l1.8 1.8M5.6 18.4l1.8-1.8M16.6 7.4l1.8-1.8" /></Icon>
);
export const IconClock = () => <Icon><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 2" /></Icon>;
export const IconSpark = () => (
  <Icon><path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5L18 18M6 18l2.5-2.5M15.5 8.5L18 6" /></Icon>
);
export const IconEye = () => (
  <Icon><path d="M2.5 12C5 7.5 8.2 5.5 12 5.5s7 2 9.5 6.5c-2.5 4.5-5.7 6.5-9.5 6.5S5 16.5 2.5 12z" /><circle cx="12" cy="12" r="3" /></Icon>
);
export const IconBuilding = () => (
  <Icon><path d="M4 20V6l8-3 8 3v14" /><path d="M9 20v-4h6v4M8 9h2M14 9h2M8 12.5h2M14 12.5h2" /></Icon>
);
export const IconGlasses = () => (
  <Icon><circle cx="7" cy="14" r="3.5" /><circle cx="17" cy="14" r="3.5" /><path d="M10.5 14h3M3.5 13l1.5-5h2M20.5 13L19 8h-2" /></Icon>
);
export const IconCheck = () => <Icon><path d="M5 12.5l4.5 4.5L19 7.5" /></Icon>;
export const IconArrow = () => <Icon><path d="M5 12h14M13 6l6 6-6 6" /></Icon>;
export const IconMenu = () => <Icon><path d="M4 7h16M4 12h16M4 17h16" /></Icon>;
export const IconLock = () => (
  <Icon><rect x="5" y="10.5" width="14" height="10" rx="2" /><path d="M8 10.5V8a4 4 0 0 1 8 0v2.5" /></Icon>
);
export const IconGlobe = () => (
  <Icon><circle cx="12" cy="12" r="8.5" /><path d="M3.5 12h17M12 3.5c2.5 2.6 3.5 5.4 3.5 8.5s-1 5.9-3.5 8.5c-2.5-2.6-3.5-5.4-3.5-8.5s1-5.9 3.5-8.5z" /></Icon>
);
