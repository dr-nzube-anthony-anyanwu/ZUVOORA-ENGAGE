/**
 * Illustrative product previews for the public site. They reproduce the real interface (widget,
 * inbox, booking panel, document review, analytics) with a fictional sample clinic and are always
 * labelled as illustrations. They contain no real clinic or patient data.
 */
import type { ReactNode } from "react";

export const SAMPLE_CLINIC = "Lumen Eye Clinic (sample)";

function Frame({ title, label, children, className = "" }: {
  title: string; label: string; children: ReactNode; className?: string;
}) {
  return (
    <figure className={`mk-preview ${className}`}>
      <div className="mk-preview-bar" aria-hidden="true"><span /><span /><span /><em>{title}</em></div>
      <div className="mk-preview-body">{children}</div>
      <figcaption className="mk-preview-caption">{label}</figcaption>
    </figure>
  );
}

/** The chat widget as a patient sees it. */
export function ChatPreview() {
  return (
    <figure className="mk-chat" aria-label="Illustrative chat conversation with a sample clinic">
      <div className="mk-chat-head">
        <div>
          <strong>Lumen Eye Clinic</strong>
          <span>Clinic assistant · replies from approved clinic information</span>
        </div>
        <span className="mk-chat-dot" aria-hidden="true" />
      </div>
      <ol className="mk-chat-log">
        <li className="mk-msg mk-msg-assistant">Hello! I can help with our services, opening hours and appointments. How can I help?</li>
        <li className="mk-msg mk-msg-visitor">Do you offer glaucoma screening?</li>
        <li className="mk-msg mk-msg-assistant">
          Yes — glaucoma screening is part of our comprehensive eye examination (about 45 minutes).
          Would you like to see available appointment times?
        </li>
        <li className="mk-msg mk-msg-visitor">Yes please, Saturday if possible.</li>
        <li className="mk-msg mk-msg-assistant mk-slots">
          <span>Saturday, 10:00</span><span>Saturday, 11:30</span><span>Saturday, 12:15</span>
        </li>
      </ol>
      <div className="mk-chat-actions" aria-hidden="true">
        <span>Book an appointment</span><span>Opening hours</span><span>Contact the clinic team</span>
      </div>
      <figcaption className="mk-chat-caption">Illustrative example · sample clinic, not a live conversation</figcaption>
    </figure>
  );
}

export function InboxPreview() {
  return (
    <Frame title="Inbox" label="Illustrative — the staff inbox with call-back requests">
      <div className="pv-tabs"><b>Needs follow-up · 2</b><span>Resolved</span><span>All conversations</span></div>
      <ul className="pv-list">
        <li><div><strong>Call-back request</strong><span>Asked about contact lens fitting for a child</span></div><em className="pv-badge pv-warn">New</em></li>
        <li><div><strong>Call-back request</strong><span>Wants to change an appointment time</span></div><em className="pv-badge pv-info">In progress</em></li>
        <li><div><strong>Conversation</strong><span>Opening hours on public holidays · answered</span></div><em className="pv-badge pv-good">Resolved</em></li>
      </ul>
    </Frame>
  );
}

export function BookingPreview() {
  return (
    <Frame title="Book an appointment" label="Illustrative — booking inside the chat, confirmed by the clinic's calendar">
      <p className="pv-step">1 · Appointment type</p>
      <div className="pv-choices"><b>Eye examination · 45 min</b><span>Contact lens fitting · 30 min</span></div>
      <p className="pv-step">2 · Choose a time <small>(shown in your time zone)</small></p>
      <div className="pv-slots"><span>Thu 09:00</span><b>Thu 10:30</b><span>Fri 14:00</span><span>Sat 11:30</span></div>
      <p className="pv-confirm">✓ Booked only after the clinic&apos;s calendar confirms it</p>
    </Frame>
  );
}

export function KnowledgePreview() {
  return (
    <Frame title="Documents" label="Illustrative — nothing reaches patients until a person approves it">
      <ul className="pv-list">
        <li><div><strong>Price list 2026</strong><span>Photo · read by AI · awaiting review</span></div><em className="pv-badge pv-warn">Review</em></li>
        <li><div><strong>Payment and HMO policy</strong><span>PDF · version 2 is live</span></div><em className="pv-badge pv-good">Live</em></li>
        <li><div><strong>Preparing for dilation</strong><span>Word · version 1 is live</span></div><em className="pv-badge pv-good">Live</em></li>
      </ul>
    </Frame>
  );
}

export function AnalyticsPreview() {
  const bars = [38, 52, 44, 61, 57, 72, 66];
  return (
    <Frame title="Analytics · last 7 days" label="Illustrative — numbers are examples, not results">
      <div className="pv-stats">
        <div><strong>148</strong><span>conversations</span></div>
        <div><strong>23</strong><span>bookings</span></div>
        <div><strong>9</strong><span>call-backs</span></div>
      </div>
      <div className="pv-bars" aria-hidden="true">
        {bars.map((h, i) => <span key={i} style={{ height: `${h}%` }} />)}
      </div>
    </Frame>
  );
}

export function TeamPreview() {
  return (
    <Frame title="Team" label="Illustrative — every person has a role; access is by invitation">
      <ul className="pv-list">
        <li><div><strong>Clinic owner</strong><span>Everything, including plan and team</span></div><em className="pv-badge pv-info">Owner</em></li>
        <li><div><strong>Practice manager</strong><span>Content, documents, analytics</span></div><em className="pv-badge pv-info">Admin</em></li>
        <li><div><strong>Front desk</strong><span>Inbox, call-backs and appointments</span></div><em className="pv-badge pv-info">Receptionist</em></li>
      </ul>
    </Frame>
  );
}
