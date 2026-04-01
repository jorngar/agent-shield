export interface ChatBoxProps {
  userMsg: string;
  userTyped: string;
  userTypingDone: boolean;
  enterPressed: boolean;
  messageSent: boolean;
  showAiDots: boolean;
  aiTyped: string;
  showAiResponse: boolean;
  aiTypingDone: boolean;
}

export function ChatBox({
  userMsg,
  userTyped,
  userTypingDone,
  enterPressed,
  messageSent,
  showAiDots,
  aiTyped,
  showAiResponse,
  aiTypingDone,
}: ChatBoxProps) {
  return (
    <div className="relative rounded-xl border border-border bg-card/80 backdrop-blur-sm shadow-2xl overflow-hidden">
      {/* Title bar */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-border/50">
        <div className="w-3 h-3 rounded-full bg-danger/80" />
        <div className="w-3 h-3 rounded-full bg-amber/80" />
        <div className="w-3 h-3 rounded-full bg-mint/80" />
        <span className="ml-2 text-xs text-muted-foreground/60 font-mono">
          agent-shield
        </span>
      </div>

      {/* Chat body */}
      <div className="p-6 font-mono min-h-[260px] flex flex-col gap-4">
        {/* Terminal typing */}
        {!messageSent && (
          <div className="flex items-start gap-2">
            <span className="text-teal shrink-0">$</span>
            <div>
              <span className="text-foreground text-lg">{userTyped}</span>
              {!userTypingDone && (
                <span className="inline-block w-[2px] h-5 bg-teal ml-[1px] align-middle animate-cursor" />
              )}
            </div>
          </div>
        )}

        {/* Sent bubble */}
        {messageSent && (
          <div className="flex justify-end animate-slide-up-fade">
            <div className="max-w-[80%] px-4 py-3 rounded-2xl rounded-br-sm bg-teal/20 border border-teal/30 text-foreground text-sm">
              {userMsg}
            </div>
          </div>
        )}

        {/* AI dots */}
        {showAiDots && (
          <div className="flex justify-start animate-slide-up-fade">
            <div className="px-4 py-3 rounded-2xl rounded-bl-sm bg-secondary/80 border border-border/50">
              <div className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-teal/70 animate-bounce [animation-delay:0ms]" />
                <span className="w-2 h-2 rounded-full bg-teal/70 animate-bounce [animation-delay:150ms]" />
                <span className="w-2 h-2 rounded-full bg-teal/70 animate-bounce [animation-delay:300ms]" />
              </div>
            </div>
          </div>
        )}

        {/* AI response */}
        {showAiResponse && (
          <div className="flex justify-start animate-slide-up-fade">
            <div className="max-w-[80%] px-4 py-3 rounded-2xl rounded-bl-sm bg-secondary/80 border border-border/50 text-foreground text-sm">
              <span>{aiTyped}</span>
              {!aiTypingDone && (
                <span className="inline-block w-[2px] h-4 bg-muted-foreground ml-[1px] align-middle animate-cursor" />
              )}
            </div>
          </div>
        )}
      </div>

      {/* Enter key */}
      <div className="absolute bottom-4 right-4">
        <kbd
          className={[
            "px-3 py-1.5 rounded-md border text-xs font-mono transition-all duration-150",
            enterPressed
              ? "animate-key-press-once border-teal bg-teal/15 text-foreground shadow-[0_3px_0_0_oklch(0.36_0.05_230)]"
              : "border-border/60 bg-secondary/60 text-muted-foreground/50 shadow-[0_3px_0_0_oklch(0.36_0.05_230_/_0.5)]",
          ].join(" ")}
        >
          Enter &crarr;
        </kbd>
      </div>
    </div>
  );
}
