import { redirect } from "next/navigation";

export default function ImportPage() {
  redirect("/operations?tab=import");
}
