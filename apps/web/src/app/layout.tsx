import type { Metadata } from "next";
import Script from "next/script";
import "./globals.css";
import { Providers } from "./providers";
import { Nav } from "@/components/Nav";
import { Fab } from "@/components/Fab";
import { JarvisPanel } from "@/components/JarvisPanel";

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
      <head>
        {/* Google Tag Manager */}
        <Script id="gtm" strategy="afterInteractive">{`
          (function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':
          new Date().getTime(),event:'gtm.js'});var f=d.getElementsByTagName(s)[0],
          j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=
          'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);
          })(window,document,'script','dataLayer','GTM-5VX97H46');
        `}</Script>
      </head>
      <body>
        {/* GTM noscript fallback */}
        <noscript>
          <iframe src="https://www.googletagmanager.com/ns.html?id=GTM-5VX97H46"
            height="0" width="0" style={{display:"none",visibility:"hidden"}} />
        </noscript>
        <Providers>
          <Nav />
          <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">{children}</main>
          <Fab />
          <JarvisPanel />
        </Providers>
      </body>
    </html>
  );
}
