"use client";

import { createContext, useContext } from "react";

type AdminContextType = {
  selectedWork: string;
  setSelectedWork: (id: string) => void;
};

const AdminContext = createContext<AdminContextType>({
  selectedWork: "modern_fantasy_game_01",
  setSelectedWork: () => {},
});

export const useAdminWork = () => useContext(AdminContext);
export { AdminContext };
