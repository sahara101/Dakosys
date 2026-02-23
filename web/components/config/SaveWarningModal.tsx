"use client";

import {
  Modal,
  ModalContent,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Button,
} from "@nextui-org/react";

interface SaveWarningModalProps {
  isOpen: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function SaveWarningModal({ isOpen, onConfirm, onCancel }: SaveWarningModalProps) {
  return (
    <Modal isOpen={isOpen} onClose={onCancel} className="dark">
      <ModalContent>
        <ModalHeader className="text-white">Save Configuration?</ModalHeader>
        <ModalBody>
          <p className="text-zinc-300 text-sm">
            You are about to overwrite the current <code className="text-violet-300">config.yaml</code>.
          </p>
          <p className="text-zinc-400 text-sm mt-2">
            Fields showing <code className="text-yellow-400">***MASKED***</code> will be
            preserved automatically — you do not need to re-enter secrets.
          </p>
        </ModalBody>
        <ModalFooter>
          <Button variant="flat" color="default" onPress={onCancel}>
            Cancel
          </Button>
          <Button color="secondary" onPress={onConfirm}>
            Save Config
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
}
