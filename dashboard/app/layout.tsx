import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Office Monitor",
  description: "Live office lights, fans, and power usage dashboard",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
