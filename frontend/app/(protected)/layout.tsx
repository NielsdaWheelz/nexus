import { UserButton } from "@clerk/nextjs";
import Link from "next/link";

export default function ProtectedLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center">
              <Link href="/app" className="text-2xl font-bold text-gray-900">
                Nexus
              </Link>
              <div className="ml-10 flex space-x-8">
                <Link
                  href="/app/documents"
                  className="text-gray-700 hover:text-gray-900 font-medium"
                >
                  Documents
                </Link>
              </div>
            </div>
            <UserButton />
          </div>
        </div>
      </nav>
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">{children}</main>
    </div>
  );
}
