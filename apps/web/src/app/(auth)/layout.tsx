export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen w-full items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center gap-1 text-center">
          <span className="text-lg font-semibold tracking-tight text-foreground">
            Volley <span className="text-accent">Intelligence</span>
          </span>
          <span className="text-sm text-muted-foreground">
            Post-match video analytics for coaches
          </span>
        </div>
        {children}
      </div>
    </div>
  );
}
