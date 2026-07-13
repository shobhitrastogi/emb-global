import ChatWindow from "@/components/ChatWindow";

export default function Home() {
  return (
    <main className="page">
      <header className="header">
        <h1>Northwind Gadgets</h1>
        <p>Support Assistant — policies &amp; orders</p>
      </header>
      <ChatWindow />
    </main>
  );
}
