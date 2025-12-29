// front_end/src/components/services/service-drawer.tsx
"use client";

import { Server } from "lucide-react";

import { Drawer } from "@/components/ui/drawer";
import { Service } from "@/types/service";
import ServiceForm, { ServiceFormData } from "./service-form";


interface ServiceDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  // 兼容 Service 对象或表单数据
  initialData?: Service | ServiceFormData | null;
  onSuccess: () => void;
}


export function ServiceDrawer({
  isOpen,
  onClose,
  initialData,
  onSuccess,
}: ServiceDrawerProps): JSX.Element {

  const isEdit = !!initialData;
  const title = isEdit ? "Edit Service" : "Create New Service";
  const description = undefined;


  return (
    <Drawer
      isOpen={isOpen}
      onClose={onClose}
      title={title}
      description={description}
      icon={<Server className="w-5 h-5 text-blue-500" />}
      width="w-[600px]"
    >
      {/* 确保每次打开都是新的表单实例以重置状态 */}
      {isOpen && (
        <ServiceForm
          initialData={initialData}
          onCancel={onClose}
          onSuccess={onSuccess}
        />
      )}
    </Drawer>
  );
}