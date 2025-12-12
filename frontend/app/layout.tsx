import type { Metadata } from "next"
import Script from "next/script"
import "./globals.css"

export const metadata: Metadata = {
  title: "EasyAudio – Turn Articles into Audio",
  description: "EasyAudio adds a tiny floating player to your articles with one script tag.",
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en">
      <head>
      </head>
      <body className="ea-body">
        {children}
        <Script
          src="https://hgtts.onrender.com/static/tts-widget.v1.js"
          strategy="afterInteractive"
          data-ail-api-base="https://hgtts.onrender.com"
          data-ail-tenant="ae32c78e-5b98-4fcf-aac6-d854c4abcf4c"
        />
      </body>
    </html>
  )
}
