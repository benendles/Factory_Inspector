import type { Metadata } from "next";
import "./globals.css";
import { ActiveWorkflowBanner } from "@/components/ActiveWorkflowBanner";
import { AppSidebar } from "@/components/AppSidebar";

export const metadata: Metadata = {
  title: "Factory Inspector",
  description: "Evidence-first industrial inspection workflow dashboard.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <div className="min-h-screen lg:grid lg:grid-cols-[17rem_1fr]">
          <AppSidebar />
          <main className="min-w-0 px-4 py-6 sm:px-8 lg:px-10"><ActiveWorkflowBanner />{children}</main>
        </div>
      </body>
    </html>
  );
}
