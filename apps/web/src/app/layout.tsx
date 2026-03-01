import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";
import { Nav } from "@/components/Nav";
import { Fab } from "@/components/Fab";

export const metadata: Metadata = {
  title: {
    default: "Stock Ledger",
    template: "%s | Stock Ledger",
  },
  description: "Personal portfolio ledger",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-TW">
      <body>
        <Providers>
          <Nav />
          <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">{children}</main>
          <Fab />
        </Providers>
      </body>
    </html>
  );
}
