import { redirect } from "next/navigation";

export default function ReviewRedirect() {
  redirect("/coach?tab=review");
}
