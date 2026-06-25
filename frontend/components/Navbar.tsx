import Link from "next/link";

export default function Navbar() {
  return (
    <header className="border-b border-gray-200">
      <nav className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
        <Link href="/" className="text-lg font-bold text-gray-900">
          GuideGenie
        </Link>
        <ul className="flex items-center gap-6 text-sm font-medium text-gray-600">
          <li>
            <Link href="/dashboard" className="hover:text-gray-900">
              Dashboard
            </Link>
          </li>
          <li>
            <Link href="/trips/new" className="hover:text-gray-900">
              New Trip
            </Link>
          </li>
        </ul>
      </nav>
    </header>
  );
}
