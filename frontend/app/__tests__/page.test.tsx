import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import Home from "../page";

describe("Home page", () => {
  it("renders heading", () => {
    render(<Home />);
    const heading = screen.getByRole("heading", {
      name: /nexus v1 frontend skeleton/i,
    });
    expect(heading).toBeInTheDocument();
  });

  it("renders welcome text", () => {
    render(<Home />);
    const text = screen.getByText(/Welcome to Nexus/i);
    expect(text).toBeInTheDocument();
  });
});
