import type { Metadata } from "next";
import Link from "next/link";
import MobileNav from "@/components/MobileNav";
import "./globals.css";

export const metadata: Metadata = {
  title: "Australian Legislation Cost Analysis",
  description: "Explore compliance and enforcement costs of Australian legislation",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased min-h-screen">
        {/* Skip to main content link for keyboard users */}
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-50 focus:px-4 focus:py-2 focus:bg-blue-600 focus:text-white focus:rounded-md focus:outline-none"
        >
          Skip to main content
        </a>

        <header className="border-b border-gray-200 dark:border-gray-800">
          <div className="max-w-7xl mx-auto px-4 py-4">
            <nav
              className="flex items-center justify-between"
              aria-label="Main navigation"
            >
              <Link
                href="/"
                className="text-lg sm:text-xl font-semibold focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 rounded-sm"
              >
                AU Legislation Costs
              </Link>

              {/* Desktop navigation */}
              <div className="hidden md:flex gap-6" role="list">
                <Link
                  href="/"
                  className="text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 rounded-sm transition-colors"
                  role="listitem"
                >
                  Browse
                </Link>
                <Link
                  href="/topics"
                  className="text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 rounded-sm transition-colors"
                  role="listitem"
                >
                  Topics
                </Link>
              </div>

              {/* Mobile navigation */}
              <MobileNav />
            </nav>
          </div>
        </header>

        <main id="main-content" className="max-w-7xl mx-auto px-4 py-6 sm:py-8">
          {children}
        </main>

        <footer className="border-t border-gray-200 dark:border-gray-800 mt-16">
          <div className="max-w-7xl mx-auto px-4 py-6 text-center text-gray-500 text-sm">
            Data from{" "}
            <a
              href="https://huggingface.co/datasets/isaacus/open-australian-legal-corpus"
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-600 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 rounded-sm"
            >
              Open Australian Legal Corpus
            </a>
            . Analysis by Claude.
          </div>
        </footer>
      </body>
    </html>
  );
}
