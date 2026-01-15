"use client";

/**
 * Global Error Boundary
 *
 * WHY: Prevents the entire app from crashing when an error occurs.
 * Displays a user-friendly error message and allows recovery via retry.
 * Next.js App Router requires error boundaries to be client components.
 */

import { useEffect } from "react";
import Link from "next/link";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Log error to console in development
    console.error("Application error:", error);
  }, [error]);

  return (
    <div className="text-center py-16">
      <h1 className="text-4xl font-bold mb-4 text-red-600 dark:text-red-400">
        Something went wrong
      </h1>
      <p className="text-gray-600 dark:text-gray-400 mb-8 max-w-md mx-auto">
        An error occurred while loading this page. This has been logged and we&apos;ll
        look into it.
      </p>
      <div className="space-x-4">
        <button
          onClick={reset}
          className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
        >
          Try again
        </button>
        <Link
          href="/"
          className="px-4 py-2 border border-gray-300 dark:border-gray-700 rounded-md hover:bg-gray-100 dark:hover:bg-gray-800 inline-block"
        >
          Go home
        </Link>
      </div>
      {process.env.NODE_ENV === "development" && (
        <details className="mt-8 text-left max-w-2xl mx-auto">
          <summary className="cursor-pointer text-sm text-gray-500 hover:text-gray-700">
            Error details (development only)
          </summary>
          <pre className="mt-2 p-4 bg-gray-100 dark:bg-gray-900 rounded text-xs overflow-auto">
            {error.message}
            {error.stack && `\n\n${error.stack}`}
          </pre>
        </details>
      )}
    </div>
  );
}
