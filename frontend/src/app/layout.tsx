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
      <body className="min-h-full flex flex-col bg-[#0A0A0A] text-[#F5F5F5] font-sans overflow-x-hidden w-full max-w-full">
        {children}
      </body>
    </html>
  );
}
