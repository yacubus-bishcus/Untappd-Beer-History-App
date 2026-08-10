import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: {
    default: "Beer History — Your tasting archive",
    template: "%s · Beer History",
  },
  description:
    "A private, searchable home for your Untappd beer history, ratings, and tasting trends.",
  applicationName: "Untappd Beer History",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "Beer History",
  },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body>{children}</body>
    </html>
  );
}
