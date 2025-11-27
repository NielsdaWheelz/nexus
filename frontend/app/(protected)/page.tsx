import Link from "next/link";

export default function AppHome() {
  return (
    <div className="text-center">
      <h1 className="text-4xl font-bold text-gray-900 mb-4">Welcome to Nexus</h1>
      <p className="text-xl text-gray-600 mb-8">
        Your reading-first knowledge management system
      </p>
      <Link
        href="/app/documents"
        className="inline-block bg-blue-600 text-white px-6 py-3 rounded-lg font-medium hover:bg-blue-700"
      >
        View Documents
      </Link>
    </div>
  );
}
