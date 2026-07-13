import "./globals.css";
import { ReactNode } from "react";

export const metadata = {
  title: "Northwind Gadgets Support",
  description: "Chatbot over policy documents and order data",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
