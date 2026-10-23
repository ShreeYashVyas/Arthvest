import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Arthvest | Macro Intelligence",
  description:
    "A transparent macroeconomic intelligence terminal for global and Indian market conditions.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
