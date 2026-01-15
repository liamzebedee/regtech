/**
 * Global Loading State
 *
 * WHY: Provides visual feedback during page transitions and data fetching.
 * Next.js App Router shows this automatically during server component loading.
 * Improves perceived performance by giving users immediate feedback.
 */

export default function Loading() {
  return (
    <div className="flex flex-col items-center justify-center py-16">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mb-4"></div>
      <p className="text-gray-500 dark:text-gray-400">Loading...</p>
    </div>
  );
}
