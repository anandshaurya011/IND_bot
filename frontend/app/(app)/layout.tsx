import { UserButton } from "@clerk/nextjs";
import type { ReactNode } from "react";
import { Nav } from "@/components/Nav";

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <header>
        <h1>NSE Scanner</h1>
        <div className="right">
          <UserButton />
        </div>
      </header>
      <Nav />
      <main>{children}</main>
    </>
  );
}
