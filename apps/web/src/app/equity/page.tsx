// Legacy equity page — redirects to /portfolio
import { redirect } from "next/navigation";

export default function EquityPage() {
  redirect("/portfolio");
}
