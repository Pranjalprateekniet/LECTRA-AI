import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Lectra — Data Ingestion Dashboard",
  description: "Grounded YouTube Revision RAG Engine",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="h-full antialiased dark">
      <body className="min-h-full flex flex-col bg-slate-950 text-slate-100 font-sans">
        {children}
      </body>
    </html>
  );
}
