from message_system_db_manager import DatabaseManager
from message_system_db_model import MessageAttachment, Attachment, P2PMessage
import json
import hashlib



class DatabaseManagerAttachments(DatabaseManager):
    def __init__(self, uri='sqlite:///freedata-messages.db'):
        super().__init__(uri)


    def add_attachment(self, session, message, attachment_data):
        """
        Adds an attachment to a message, either by creating a new attachment or reusing an existing one.

        Args:
        - session: The current database session.
        - message: The P2PMessage instance to which the attachment should be linked.
        - attachment_data: A dictionary containing the attachment's data.

        Returns:
        - The Attachment instance.
        """
        hash_sha512 = hashlib.sha512(attachment_data['data'].encode()).hexdigest()
        existing_attachment = session.query(Attachment).filter_by(hash_sha512=hash_sha512).first()

        if not existing_attachment:
            attachment = Attachment(
                name=attachment_data['name'],
                data_type=attachment_data['type'],
                data=attachment_data['data'],
                checksum_crc32=attachment_data.get('checksum_crc32', ''),
                hash_sha512=hash_sha512
            )
            session.add(attachment)
            session.flush()  # Ensure the attachment is persisted and has an ID
        else:
            attachment = existing_attachment

        # Link the message and the attachment through MessageAttachment
        link = MessageAttachment(message=message, attachment=attachment)
        self.log(f"Added attachment to database: {attachment.name}")
        session.add(link)
        return attachment

    def get_attachments_by_message_id(self, message_id):
        session = self.get_thread_scoped_session()
        try:
            # Fetch the message by its ID
            message = session.query(P2PMessage).filter_by(id=message_id).first()
            if message:
                # Navigate through the association to get attachments
                attachments = [ma.attachment.to_dict() for ma in message.message_attachments]
                return attachments
            else:
                return []
        except Exception as e:
            self.log(f"Error fetching attachments for message ID {message_id}: {e}", isWarning=True)
            return []
        finally:
            session.remove()

    def get_attachments_by_message_id_json(self, message_id):
        attachments = self.get_attachments_by_message_id(message_id)
        return json.dumps(attachments)