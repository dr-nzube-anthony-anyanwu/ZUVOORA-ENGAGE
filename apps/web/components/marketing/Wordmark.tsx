import Image from "next/image";
import logo from "@/public/brand/zuvoora-engage-logo.png";

export const TAGLINE = "Patient Communication & Engagement Platform for Eye Care";

/**
 * The official ZUVOORA Engage logo (symbol + wordmark). Source artwork: docs/brand/. The tagline
 * from the artwork is rendered as real text where there is room (`withTagline`), because at logo
 * size it would be too small to read. The logo is designed for light backgrounds only.
 */
export function Wordmark({ size = "md", withTagline = false, priority = false, alt = "ZUVOORA Engage" }: {
  size?: "sm" | "md" | "lg"; withTagline?: boolean; priority?: boolean;
  /** Use e.g. "ZUVOORA Engage home" when the logo is the only content of a link. */
  alt?: string;
}) {
  return (
    <span className={`logo logo-${size}`}>
      <Image src={logo} alt={alt} priority={priority} className="logo-img" />
      {withTagline && <span className="logo-tagline">{TAGLINE}</span>}
    </span>
  );
}
