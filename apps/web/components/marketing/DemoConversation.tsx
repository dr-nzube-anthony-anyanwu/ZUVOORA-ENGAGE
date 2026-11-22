"use client";

/**
 * Scripted demonstration of the patient experience. No AI is called, nothing is sent or stored:
 * each question has a fixed, pre-written answer modelled on how Engage behaves.
 */
import { useState } from "react";

type Step = { question: string; answer: string; note: string };

const SCRIPT: Step[] = [
  {
    question: "What time do you open on Saturday?",
    answer: "On Saturdays we are open from 9:00 to 13:00. We are closed on Sundays and public holidays.",
    note: "Answered from the clinic's published opening hours.",
  },
  {
    question: "How much is an eye examination?",
    answer: "A comprehensive eye examination costs ₦25,000 and takes about 45 minutes. Would you like to book one?",
    note: "Answered from the clinic's published services and prices.",
  },
  {
    question: "My eye suddenly went dark — what should I do?",
    answer: "This sounds like it could be urgent. I can't assess symptoms. Please go to the nearest emergency unit now, or call the clinic straight away.",
    note: "Urgent symptoms always get emergency guidance first — never a diagnosis.",
  },
  {
    question: "Which eye drops should I use for dry eyes?",
    answer: "I'm not able to recommend medicines or treatment. A clinician at the clinic can help — would you like the clinic team to contact you?",
    note: "Medical questions are passed to people, not answered by AI.",
  },
  {
    question: "Do you accept my insurance plan?",
    answer: "I don't have that information. Would you like the clinic team to contact you?",
    note: "When the clinic hasn't published an answer, Engage says so instead of guessing.",
  },
];

export function DemoConversation() {
  const [asked, setAsked] = useState<number[]>([]);
  const remaining = SCRIPT.map((_, i) => i).filter((i) => !asked.includes(i));

  return (
    <div className="mk-demo">
      <div className="mk-demo-window">
        <div className="mk-chat-head">
          <div>
            <strong>Lumen Eye Clinic</strong>
            <span>Scripted demonstration · sample clinic</span>
          </div>
        </div>
        <ol className="mk-chat-log" aria-live="polite" aria-label="Demonstration conversation">
          <li className="mk-msg mk-msg-assistant">Hello! Choose a question below to see how the assistant responds.</li>
          {asked.map((i) => (
            <li key={i} className="mk-demo-pair">
              <span className="mk-msg mk-msg-visitor">{SCRIPT[i].question}</span>
              <span className="mk-msg mk-msg-assistant">{SCRIPT[i].answer}</span>
              <span className="mk-demo-note">{SCRIPT[i].note}</span>
            </li>
          ))}
        </ol>
      </div>
      <div className="mk-demo-questions">
        <h3>Try a question</h3>
        {remaining.length > 0 ? (
          <ul>
            {remaining.map((i) => (
              <li key={i}>
                <button type="button" className="mk-chip" onClick={() => setAsked([...asked, i])}>
                  {SCRIPT[i].question}
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p>That&apos;s the whole demonstration.</p>
        )}
        {asked.length > 0 && (
          <button type="button" className="mk-link-button" onClick={() => setAsked([])}>Start again</button>
        )}
        <p className="mk-fineprint">
          A pre-written script for illustration. In a real clinic, answers come from the information
          that clinic has approved, and staff can take over at any time.
        </p>
      </div>
    </div>
  );
}
